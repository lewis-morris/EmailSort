from __future__ import annotations

import logging
import time
from datetime import timedelta, timezone
from typing import Any, Dict, List, Optional

import requests  # type: ignore[import]

from .utils import utc_now

logger = logging.getLogger("email_categorise.graph")


def _plan_category_updates(
    desired: Dict[str, str], existing: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Return the operations needed to align master categories with desired colours.

    The returned dict is keyed by category name and each value contains:
    - action: one of create/update/unchanged
    - color: desired categoryColor value
    - id: master category id when present in Graph
    """

    existing_by_name = {
        c.get("displayName"): c for c in existing if c.get("displayName")
    }
    plan: Dict[str, Dict[str, Any]] = {}

    for name, color in desired.items():
        current = existing_by_name.get(name)
        if current is None:
            plan[name] = {"action": "create", "color": color}
            continue

        if current.get("color") != color:
            plan[name] = {"action": "update", "color": color, "id": current.get("id")}
            continue

        plan[name] = {"action": "unchanged", "color": color, "id": current.get("id")}

    return plan


class GraphClient:
    """Thin Microsoft Graph wrapper scoped to a single user/mailbox."""

    def __init__(
        self,
        access_token: str,
        user: str,
        base_url: str = "https://graph.microsoft.com/v1.0",
    ) -> None:
        self.access_token = access_token
        self.user = user  # "me" for delegated, or userPrincipalName for app-only
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        )

    @property
    def _user_root(self) -> str:
        if self.user.lower() == "me":
            return f"{self.base_url}/me"
        return f"{self.base_url}/users/{self.user}"

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self.session.get(url, params=params)
        if not resp.ok:
            logger.error("Graph GET %s failed: %s", resp.url, resp.text)
            resp.raise_for_status()
        return resp.json()

    def _patch(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.patch(url, json=body)
        if not resp.ok:
            logger.error("Graph PATCH %s failed: %s", resp.url, resp.text)
            resp.raise_for_status()
        return resp.json() if resp.text else {}

    def _post(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.post(url, json=body)
        if not resp.ok:
            logger.error("Graph POST %s failed: %s", resp.url, resp.text)
            resp.raise_for_status()
        return resp.json() if resp.text else {}

    def _delete(self, url: str) -> None:
        resp = self.session.delete(url)
        if not resp.ok:
            logger.error("Graph DELETE %s failed: %s", resp.url, resp.text)
            resp.raise_for_status()

    def list_inbox_unprocessed_messages(
        self, days_back: int, max_messages: int = 100
    ) -> List[Dict[str, Any]]:
        """Return recent inbox messages that have not yet been tagged as Processed."""
        since = utc_now() - timedelta(days=days_back)
        since_str = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = f"{self._user_root}/mailFolders/Inbox/messages"
        params: Dict[str, Any] = {
            "$select": "id,subject,from,receivedDateTime,bodyPreview,uniqueBody,conversationId,categories,flag,importance,isRead,webLink",
            "$orderby": "receivedDateTime desc",
            "$filter": f"receivedDateTime ge {since_str} and not(categories/any(c:c eq 'Processed'))",
            "$top": min(max_messages, 50),
        }
        messages: List[Dict[str, Any]] = []
        while url and len(messages) < max_messages:
            data = self._get(url, params=params)
            params = None
            messages.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            if not url:
                break
        return messages[:max_messages]

    def list_inbox_messages_since(
        self, days_back: int, max_messages: int = 500
    ) -> List[Dict[str, Any]]:
        since = utc_now() - timedelta(days=days_back)
        since_str = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = f"{self._user_root}/mailFolders/Inbox/messages"
        params: Dict[str, Any] = {
            "$select": "id,subject,from,receivedDateTime,bodyPreview,conversationId,categories,isRead,webLink",
            "$orderby": "receivedDateTime desc",
            "$filter": f"receivedDateTime ge {since_str}",
            "$top": min(max_messages, 50),
        }
        out: List[Dict[str, Any]] = []
        while url and len(out) < max_messages:
            data = self._get(url, params=params)
            params = None
            out.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            if not url:
                break
        return out[:max_messages]

    def list_sent_messages_since(
        self, days_back: int, max_messages: int = 500
    ) -> List[Dict[str, Any]]:
        since = utc_now() - timedelta(days=days_back)
        since_str = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = f"{self._user_root}/mailFolders/SentItems/messages"
        params: Dict[str, Any] = {
            "$select": "id,subject,body,bodyPreview,from,toRecipients,ccRecipients,sentDateTime",
            "$orderby": "sentDateTime desc",
            "$filter": f"sentDateTime ge {since_str}",
            "$top": min(max_messages, 50),
        }
        out: List[Dict[str, Any]] = []
        while url and len(out) < max_messages:
            data = self._get(url, params=params)
            params = None
            out.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            if not url:
                break
        return out[:max_messages]

    def list_conversation_messages(
        self, conversation_id: str, max_messages: int = 20
    ) -> List[Dict[str, Any]]:
        if not conversation_id:
            return []
        conv_id = conversation_id.replace("'", "''")
        url = f"{self._user_root}/messages"
        params: Dict[str, Any] = {
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,bodyPreview,uniqueBody,isRead",
            "$filter": f"conversationId eq '{conv_id}'",
            "$top": min(max_messages, 50),
        }
        out: List[Dict[str, Any]] = []
        while url and len(out) < max_messages:
            data = self._get(url, params=params)
            params = None
            out.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            if not url:
                break
        # Graph can return 400 InefficientFilter when combining conversationId
        # filter with server-side ordering; sort locally instead.
        out = sorted(
            out,
            key=lambda m: m.get("receivedDateTime") or m.get("sentDateTime") or "",
        )
        return out[:max_messages]

    def update_message(self, message_id: str, patch_body: Dict[str, Any]) -> None:
        self._patch(f"{self._user_root}/messages/{message_id}", patch_body)

    def create_draft_reply(
        self, message_id: str, reply_body_html: str
    ) -> Optional[str]:
        """Create a draft reply for a message and return the draft id (None on failure)."""
        data = self._post(f"{self._user_root}/messages/{message_id}/createReply", {})
        draft = data.get("message") or data
        draft_id = draft.get("id")
        if not draft_id:
            logger.error("createReply did not return a draft id for %s", message_id)
            return None
        self._patch(
            f"{self._user_root}/messages/{draft_id}",
            {"body": {"contentType": "HTML", "content": reply_body_html}},
        )
        return draft_id

    def delete_message(self, message_id: str) -> None:
        self._delete(f"{self._user_root}/messages/{message_id}")

    def send_mail(
        self, subject: str, html_body: str, to_address: str, save_to_sent: bool = True
    ) -> None:
        body = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": html_body},
                "toRecipients": [{"emailAddress": {"address": to_address}}],
            },
            "saveToSentItems": bool(save_to_sent),
        }
        self._post(f"{self._user_root}/sendMail", body)

    def wait_for_message_by_subject(
        self,
        subject: str,
        *,
        timeout_seconds: int = 90,
        poll_interval: int = 5,
        days_back: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """Poll the inbox until a message with the exact subject arrives.

        Returns the message dict or None if not seen before timeout.
        """

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            for msg in self.list_inbox_messages_since(
                days_back=days_back, max_messages=200
            ):
                if (msg.get("subject") or "").strip() == subject:
                    return msg
            time.sleep(poll_interval)
        return None

    def send_mail_and_wait(
        self,
        subject: str,
        html_body: str,
        to_address: Optional[str] = None,
        *,
        save_to_sent: bool = True,
        wait_for_delivery: bool = True,
        timeout_seconds: int = 90,
        poll_interval: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """Send a mail (default to self) and optionally wait for it to appear in Inbox."""

        target = to_address or self.user
        self.send_mail(
            subject=subject,
            html_body=html_body,
            to_address=target,
            save_to_sent=save_to_sent,
        )
        if not wait_for_delivery:
            return None
        return self.wait_for_message_by_subject(
            subject=subject,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
        )

    def list_master_categories(self) -> List[Dict[str, Any]]:
        url = f"{self._user_root}/outlook/masterCategories"
        params = {"$select": "id,displayName,color"}
        out: List[Dict[str, Any]] = []
        while url:
            data = self._get(url, params=params)
            params = None
            out.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        return out

    def create_master_category(self, display_name: str, color: str) -> Dict[str, Any]:
        body = {"displayName": display_name, "color": color}
        return self._post(f"{self._user_root}/outlook/masterCategories", body)

    def update_master_category(self, category_id: str, color: str) -> Dict[str, Any]:
        body = {"color": color}
        return self._patch(
            f"{self._user_root}/outlook/masterCategories/{category_id}", body
        )

    def ensure_master_categories(
        self, desired_colors: Dict[str, str]
    ) -> Dict[str, str]:
        """Create or update master categories so they carry the desired colours.

        Returns a map of category name to action taken (create/update/unchanged).
        """

        existing = self.list_master_categories()
        plan = _plan_category_updates(desired_colors, existing)
        results: Dict[str, str] = {}

        for name, step in plan.items():
            action = step.get("action")
            color = step.get("color")
            if action == "create":
                self.create_master_category(name, color)
            elif action == "update":
                cat_id = step.get("id")
                if cat_id:
                    self.update_master_category(cat_id, color)
                else:
                    logger.warning(
                        "Category %s missing id during update; recreating", name
                    )
                    self.create_master_category(name, color)
                    action = "create"

            results[name] = action or "unchanged"

        return results
