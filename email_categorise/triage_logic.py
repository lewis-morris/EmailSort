from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .auth import (
    acquire_application_token,
    acquire_delegated_token,
    build_confidential_client,
    build_public_client,
)
from .codex_runner import CodexRunner
from .config import AppConfig, AccountConfig
from .graph_client import GraphClient
from .utils import account_state_dir, load_json, save_json, utc_now

logger = logging.getLogger("email_categorise.logic")


CATEGORY_HELP = """Categories (exact strings):

- Urgent
- Priority 1
- Priority 2
- Priority 3
- Marketing
- Informational
- No reply needed
- Complete
- Possibly Complete
- Processed (added by the tool)
"""

# Colour palette for Outlook master categories.
# Graph only accepts the CategoryColor enum: none, preset0..preset24.
# We choose bright presets for urgency and darker variants for completion states.
# Mapping reference: https://learn.microsoft.com/graph/api/resources/outlookcategory
CATEGORY_COLORS = {
    "Urgent": "preset0",  # bright red
    "Priority 1": "preset1",  # orange
    "Priority 2": "preset3",  # yellow
    "Priority 3": "preset4",  # green
    "Marketing": "preset5",  # teal
    "Informational": "preset7",  # blue
    "No reply needed": "preset12",  # gray
    "Complete": "preset19",  # dark green
    "Possibly Complete": "preset18",  # dark yellow
    "Processed": "preset13",  # dark gray
}


FLAG_HELP = """Flags (exact strings):

- Today
- Tomorrow
- This week
- Next week
- No date
- Mark as complete
"""


def _trim(text: Optional[str], max_len: int = 2000) -> str:
    if not text:
        return ""
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _has_user_replied(thread_messages: List[Dict[str, Any]], account_email: str) -> bool:
    addr_lower = account_email.lower()
    for m in thread_messages:
        from_data = (m.get("from") or {}).get("emailAddress") or {}
        if (from_data.get("address") or "").lower() == addr_lower:
            return True
    return False


def _last_message_from_me(thread_messages: List[Dict[str, Any]], account_email: str) -> bool:
    if not thread_messages:
        return False
    addr_lower = account_email.lower()
    last = thread_messages[-1]
    from_data = (last.get("from") or {}).get("emailAddress") or {}
    return (from_data.get("address") or "").lower() == addr_lower


def _simplify_thread(thread_messages: List[Dict[str, Any]], account_email: str) -> List[Dict[str, Any]]:
    addr_lower = account_email.lower()
    tail = thread_messages[-8:]
    simplified: List[Dict[str, Any]] = []
    for tm in tail:
        from_data = (tm.get("from") or {}).get("emailAddress") or {}
        addr = (from_data.get("address") or "").lower()
        simplified.append(
            {
                "from_me": addr == addr_lower,
                "from_address": addr,
                "from_name": from_data.get("name"),
                "sentDateTime": tm.get("sentDateTime") or tm.get("receivedDateTime"),
                "bodyPreview": _trim(tm.get("bodyPreview"), 400),
                "isRead": tm.get("isRead"),
            }
        )
    return simplified


def _tone_profile_for_sender(tone_profiles: Dict[str, Any], sender_address: str) -> Dict[str, Any]:
    contacts = tone_profiles.get("contacts", {})
    default_profile = tone_profiles.get("default", {})
    return contacts.get(sender_address.lower(), default_profile)


def _calculate_importance(primary_category: str) -> str:
    cat = primary_category.lower()
    if cat in {"urgent", "priority 1"}:
        return "high"
    if cat in {"priority 2", "informational"}:
        return "normal"
    if cat in {"priority 3", "marketing", "no reply needed"}:
        return "low"
    return "normal"


def _build_followup_flag(flag_name: Optional[str]) -> Optional[Dict[str, Any]]:
    if not flag_name:
        return None
    name = flag_name.strip().lower()
    now = utc_now()
    start = now
    due = now

    if name == "today":
        start = now
        due = datetime(now.year, now.month, now.day, 23, 59, 0, tzinfo=timezone.utc)
    elif name == "tomorrow":
        tmr = now + timedelta(days=1)
        start = datetime(tmr.year, tmr.month, tmr.day, 9, 0, 0, tzinfo=timezone.utc)
        due = datetime(tmr.year, tmr.month, tmr.day, 18, 0, 0, tzinfo=timezone.utc)
    elif name == "this week":
        days_ahead = 4 - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        target = now + timedelta(days=days_ahead)
        start = now
        due = datetime(target.year, target.month, target.day, 18, 0, 0, tzinfo=timezone.utc)
    elif name == "next week":
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        monday_next = now + timedelta(days=days_until_monday)
        friday_next = monday_next + timedelta(days=4)
        start = monday_next
        due = datetime(friday_next.year, friday_next.month, friday_next.day, 18, 0, 0, tzinfo=timezone.utc)
    elif name == "no date":
        return {"flagStatus": "flagged", "startDateTime": None, "dueDateTime": None, "completedDateTime": None}
    elif name == "mark as complete":
        return {
            "flagStatus": "complete",
            "completedDateTime": {"dateTime": utc_now().replace(microsecond=0).isoformat(), "timeZone": "UTC"},
            "startDateTime": None,
            "dueDateTime": None,
        }
    else:
        return None

    return {
        "flagStatus": "flagged",
        "startDateTime": {"dateTime": start.replace(microsecond=0).isoformat(), "timeZone": "UTC"},
        "dueDateTime": {"dateTime": due.replace(microsecond=0).isoformat(), "timeZone": "UTC"},
        "completedDateTime": None,
    }


def _triage_prompt() -> str:
    return (
        "You triage email for a busy software developer.\n"
        "You will be given JSON with an array of messages under key 'messages'.\n"
        "For each message, output exactly one decision object containing:\n"
        "- id (must match)\n"
        "- primary_category (exact string from the list)\n"
        "- secondary_categories (array, may be empty)\n"
        "- flag (Today/Tomorrow/This week/Next week/No date/Mark as complete or null)\n"
        "- needs_reply (boolean)\n"
        "- is_marketing (boolean)\n"
        "- is_informational (boolean)\n"
        "- mark_complete (boolean)\n"
        "- mark_possibly_complete (boolean)\n"
        "- pin (boolean)\n"
        "- create_task (boolean)\n"
        "- task_summary (string or null)\n"
        "- summary (string or null)\n"
        "- draft_reply_body (string or null)\n\n"
        f"{CATEGORY_HELP}\n"
        f"{FLAG_HELP}\n\n"
        "Rules:\n"
        "- Only set mark_complete=true when you are very confident there is no remaining action.\n"
        "- When in doubt, set mark_possibly_complete=true instead.\n"
        "- Marketing only for obvious newsletters/promotions.\n"
        "- Informational for messages that provide info but don't clearly require action.\n"
        "- If needs_reply=true, produce a draft_reply_body using the provided tone_profile.\n"
    )


def _ensure_category_colors(graph: GraphClient) -> None:
    """Make sure Outlook master categories carry the desired colours.

    Safe to call repeatedly; only creates/updates mismatched categories.
    """

    try:
        graph.ensure_master_categories(CATEGORY_COLORS)
    except Exception as exc:
        logger.warning("Unable to ensure category colours: %s", exc)


def _tone_prompt() -> str:
    return (
        "You analyse example emails and summarise the author's writing style.\n"
        "Return JSON only with keys: contact_email, tone_summary, style_guidelines (array of strings).\n"
        "Style guidelines should be actionable (greeting, brevity, sign-off, formality)."
    )


def _apply_triage_to_message(
    original: Dict[str, Any],
    triage: Dict[str, Any],
    draft_replies: bool,
    create_tasks: bool,
    graph: GraphClient,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
    existing_categories: List[str] = list(original.get("categories") or [])
    categories = set(existing_categories)
    categories.add("Processed")

    primary_category = triage.get("primary_category") or "Priority 3"
    categories.add(primary_category)

    for extra in triage.get("secondary_categories") or []:
        categories.add(str(extra))

    if triage.get("is_marketing"):
        categories.add("Marketing")
    if triage.get("is_informational"):
        categories.add("Informational")

    if triage.get("mark_complete"):
        categories.add("Complete")
        categories.discard("Possibly Complete")
    elif triage.get("mark_possibly_complete"):
        categories.add("Possibly Complete")

    flag_obj = _build_followup_flag(triage.get("flag"))

    is_marketing = bool(triage.get("is_marketing"))
    is_informational = bool(triage.get("is_informational"))
    needs_reply = bool(triage.get("needs_reply"))
    mark_complete = bool(triage.get("mark_complete"))
    create_task = bool(triage.get("create_task")) if create_tasks else False

    if mark_complete or is_marketing:
        is_read = True
    elif is_informational:
        is_read = False
    else:
        is_read = False  # keep unread by default, conservative

    patch_body: Dict[str, Any] = {
        "categories": sorted(categories),
        "isRead": is_read,
        "importance": _calculate_importance(primary_category),
    }
    if flag_obj is not None:
        patch_body["flag"] = flag_obj

    # informational summary
    info_entry: Optional[Dict[str, Any]] = None
    if is_informational and triage.get("summary"):
        from_data = (original.get("from") or {}).get("emailAddress") or {}
        info_entry = {
            "subject": original.get("subject"),
            "from": from_data.get("address"),
            "from_name": from_data.get("name"),
            "summary": triage.get("summary"),
            "webLink": original.get("webLink"),
        }

    task_entry: Optional[Dict[str, Any]] = None
    if create_task and triage.get("task_summary"):
        task_entry = {
            "subject": original.get("subject"),
            "task_summary": triage.get("task_summary"),
            "webLink": original.get("webLink"),
        }

    draft_id: Optional[str] = None
    if draft_replies and needs_reply and triage.get("draft_reply_body"):
        html = "<p>" + "<br>".join(str(triage["draft_reply_body"]).splitlines()) + "</p>"
        draft_id = graph.create_draft_reply(original["id"], html)

    return patch_body, info_entry, task_entry, draft_id


def _write_tasks_file(account_dir: Path, tasks: List[Dict[str, Any]]) -> None:
    if not tasks:
        return
    path = account_dir / "tasks.md"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n## Run {utc_now().isoformat()}\n")
        for t in tasks:
            subject = t.get("subject") or "(no subject)"
            summary = t.get("task_summary") or ""
            link = t.get("webLink") or ""
            if link:
                f.write(f"- [{subject}]({link}) - {summary}\n")
            else:
                f.write(f"- {subject} - {summary}\n")


def _write_log_file(account_dir: Path, messages: List[Dict[str, Any]], triage_map: Dict[str, Dict[str, Any]]) -> None:
    path = account_dir / "triage-log.txt"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n=== Triage run at {utc_now().isoformat()} ===\n")
        for msg in messages:
            t = triage_map.get(msg["id"]) or {}
            f.write(f"* {msg.get('subject')}\n")
            f.write(f"  primary: {t.get('primary_category')} flag: {t.get('flag')}\n")


def _summary_email_html(infos: List[Dict[str, Any]], account_email: str) -> str:
    rows = []
    for i in infos:
        subj = i.get("subject") or "(no subject)"
        who = i.get("from_name") or i.get("from") or ""
        summ = i.get("summary") or ""
        link = i.get("webLink") or ""
        header = f"{subj} (from {who})" if who else subj
        if link:
            header = f'<a href="{link}">{header}</a>'
        rows.append(f"<li><strong>{header}</strong><br>{summ}</li>")
    return f"<p>Informational email summary for <strong>{account_email}</strong>.</p><ul>{''.join(rows)}</ul>"


def _get_graph(config: AppConfig, account: AccountConfig) -> GraphClient:
    tenant_id = account.tenant_id or config.azure.tenant_id
    cache_path = Path(config.auth.token_cache_path)
    if config.auth.auth_mode == "delegated":
        app = build_public_client(config.azure, cache_path, tenant_id=tenant_id)
        token = acquire_delegated_token(app, config.azure.delegated_scopes, account.email)
        if not token:
            raise RuntimeError(f"Delegated auth failed for {account.email}")
        return GraphClient(token["access_token"], user="me")
    if config.auth.auth_mode == "application":
        app = build_confidential_client(config.azure, cache_path, tenant_id=tenant_id)
        token = acquire_application_token(app)
        if not token:
            raise RuntimeError("Application auth failed")
        # app-only tokens cannot use /me, use /users/{upn}
        return GraphClient(token["access_token"], user=account.email)
    raise RuntimeError(f"Unknown auth_mode: {config.auth.auth_mode}")


def init_account(config: AppConfig, account: AccountConfig, runner_reply: CodexRunner) -> Dict[str, Any]:
    state_root = account_state_dir(Path("./data"), account.email)

    graph = _get_graph(config, account)

    inbox = graph.list_inbox_messages_since(config.triage.lookback_days_initial, max_messages=1000)
    domain = account.email.split("@")[-1].lower()
    sender_stats: Dict[str, Any] = {}
    for msg in inbox:
        fd = (msg.get("from") or {}).get("emailAddress") or {}
        addr = (fd.get("address") or "").lower()
        if not addr:
            continue
        entry = sender_stats.get(addr) or {"address": addr, "display_name": fd.get("name"), "count": 0, "internal": addr.endswith("@"+domain), "latest_received": msg.get("receivedDateTime")}
        entry["count"] += 1
        sender_stats[addr] = entry
    save_json(state_root / "sender_stats.json", sender_stats)

    # tone profiles from sent items
    sent = graph.list_sent_messages_since(config.triage.tone_profile_lookback_days, max_messages=800)
    account_addr = account.email.lower()
    recip_map: Dict[str, List[Dict[str, Any]]] = {}
    for m in sent:
        recips = (m.get("toRecipients") or []) + (m.get("ccRecipients") or [])
        for r in recips:
            ed = r.get("emailAddress") or {}
            addr = (ed.get("address") or "").lower()
            if not addr or addr == account_addr:
                continue
            recip_map.setdefault(addr, []).append(m)

    top = sorted(recip_map.items(), key=lambda kv: len(kv[1]), reverse=True)[:10]
    tone_profiles: Dict[str, Any] = {"contacts": {}, "default": {}}
    schema = Path(__file__).parent / "json_schemas" / "tone_profile.schema.json"

    def samples(msgs: List[Dict[str, Any]], n: int = 5) -> str:
        parts = []
        for i, m in enumerate(msgs[:n], start=1):
            body = (m.get("body") or {}).get("content") or m.get("bodyPreview") or ""
            parts.append(f"[EMAIL {i}]\nSubject: {m.get('subject')}\n\n{_trim(body, 1200)}")
        return "\n\n".join(parts)

    for addr, msgs in top:
        prompt = _tone_prompt() + "\n\n" + f"Contact email: {addr}\n\nExamples:\n{samples(msgs)}"
        out_path = state_root / f"tone_{addr.replace('@','_at_')}.json"
        try:
            res = runner_reply.run_with_schema(prompt, schema, out_path)
            tone_profiles["contacts"][addr] = res
        except Exception as exc:
            logger.warning("Tone profile failed for %s: %s", addr, exc)

    # default profile
    prompt = _tone_prompt() + "\n\nExamples:\n" + samples(sent[:20], n=20)
    out_path = state_root / "tone_default.json"
    try:
        res = runner_reply.run_with_schema(prompt, schema, out_path)
        res["contact_email"] = "default"
        tone_profiles["default"] = res
    except Exception as exc:
        logger.warning("Default tone profile failed: %s", exc)

    save_json(state_root / "tone_profiles.json", tone_profiles)

    state = load_json(state_root / "state.json", {"first_run_completed": False, "last_run_utc": None})
    state["first_run_completed"] = True
    save_json(state_root / "state.json", state)

    return {"account": account.email, "sender_stats": len(sender_stats), "tone_contacts": len(tone_profiles["contacts"])}


def run_for_account(config: AppConfig, account: AccountConfig, runner_triage: CodexRunner, runner_reply: CodexRunner) -> Dict[str, Any]:
    state_root = account_state_dir(Path("./data"), account.email)
    state = load_json(state_root / "state.json", {"first_run_completed": False, "last_run_utc": None})

    graph = _get_graph(config, account)

    # Ensure category colours exist before tagging messages so Outlook renders
    # the expected palette for priority / status tags.
    _ensure_category_colors(graph)

    if not state.get("first_run_completed"):
        init_account(config, account, runner_reply)
        state = load_json(state_root / "state.json", {"first_run_completed": True, "last_run_utc": None})

    days_back = config.triage.lookback_days_incremental if state.get("last_run_utc") else config.triage.lookback_days_initial
    msgs = graph.list_inbox_unprocessed_messages(days_back, max_messages=config.triage.max_messages_per_run)
    if not msgs:
        state["last_run_utc"] = utc_now().isoformat()
        save_json(state_root / "state.json", state)
        return {"account": account.email, "processed": 0}

    sender_stats = load_json(state_root / "sender_stats.json", {})
    tone_profiles = load_json(state_root / "tone_profiles.json", {"contacts": {}, "default": {}})

    payload_msgs = []
    for m in msgs:
        fd = (m.get("from") or {}).get("emailAddress") or {}
        sender_addr = (fd.get("address") or "").lower()
        conv = m.get("conversationId")
        thread = graph.list_conversation_messages(conv, max_messages=10) if conv else []
        payload_msgs.append({
            "id": m["id"],
            "subject": m.get("subject"),
            "from": {"address": sender_addr, "name": fd.get("name")},
            "receivedDateTime": m.get("receivedDateTime"),
            "categories": m.get("categories", []),
            "importance": m.get("importance"),
            "webLink": m.get("webLink"),
            "uniqueBodyHtml": (m.get("uniqueBody") or {}).get("content"),
            "thread_summary": _simplify_thread(thread, account.email),
            "has_user_replied_in_thread": _has_user_replied(thread, account.email),
            "last_message_from_me_in_thread": _last_message_from_me(thread, account.email),
            "sender_stats": sender_stats.get(sender_addr, {}),
            "tone_profile": _tone_profile_for_sender(tone_profiles, sender_addr),
        })

    schema = Path(__file__).parent / "json_schemas" / "triage_output.schema.json"
    out_path = state_root / f"triage_{utc_now().strftime('%Y%m%d-%H%M%S')}.json"

    prompt = _triage_prompt() + "\n\nINPUT JSON:\n" + json.dumps({"messages": payload_msgs}, indent=2)
    triage_res = runner_triage.run_with_schema(prompt, schema, out_path)
    results = triage_res.get("messages") or []
    triage_map = {r["id"]: r for r in results if "id" in r}

    infos = []
    tasks = []
    drafts = 0
    for m in msgs:
        t = triage_map.get(m["id"])
        if not t:
            continue
        patch, info, task, draft_id = _apply_triage_to_message(m, t, config.triage.draft_replies, config.triage.create_tasks, graph)
        graph.update_message(m["id"], patch)
        if info:
            infos.append(info)
        if task:
            tasks.append(task)
        if draft_id:
            drafts += 1

    if config.triage.create_tasks and tasks:
        _write_tasks_file(state_root, tasks)
    if config.triage.log_to_file:
        _write_log_file(state_root, msgs, triage_map)

    summary_sent = False
    if config.triage.send_summary_email and infos and config.triage.summary_email_to:
        # Send summary from the mailbox specified in config (must be configured)
        # If this run is not for that mailbox, we still send from that mailbox by creating a second GraphClient.
        from_acc = config.triage.summary_email_from_account or account.email
        from_account_obj = next((a for a in config.accounts if a.email.lower() == from_acc.lower()), None)
        if from_account_obj:
            graph_sender = _get_graph(config, from_account_obj)
            html = _summary_email_html(infos, account.email)
            graph_sender.send_mail(subject=f"Informational email summary for {account.label}", html_body=html, to_address=config.triage.summary_email_to)
            summary_sent = True

    state["last_run_utc"] = utc_now().isoformat()
    save_json(state_root / "state.json", state)

    return {"account": account.email, "processed": len(msgs), "drafts": drafts, "tasks": len(tasks), "informational": len(infos), "summary_sent": summary_sent}
