from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List, Optional

from .codex_runner import CodexRunner
from .config import load_config, AccountConfig
from .triage_logic import init_account, run_for_account
from .utils import configure_logging, load_env_file, utc_now

logger = logging.getLogger("email_categorise.cli")


def _select_accounts(accounts: List[AccountConfig], selected: Optional[List[str]]) -> List[AccountConfig]:
    if not selected:
        return accounts
    s = {x.lower() for x in selected}
    out = [a for a in accounts if a.email.lower() in s]
    if not out:
        raise SystemExit("No accounts matched -a filters")
    return out


def _write_report(repo_root: Path, name: str, content: str) -> Path:
    out_dir = repo_root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"email_categorise_{name}_{stamp}.last.md"
    path.write_text(content, encoding="utf-8")
    return path


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser("email_categorise")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--config", "-c", required=True)
    p_init.add_argument("-a", "--account", action="append")
    p_init.add_argument("-v", "--verbose", action="count", default=0)

    p_run = sub.add_parser("run")
    p_run.add_argument("--config", "-c", required=True)
    p_run.add_argument("-a", "--account", action="append")
    p_run.add_argument("-v", "--verbose", action="count", default=0)

    args = parser.parse_args()
    configure_logging(args.verbose or 0)

    cfg = load_config(args.config)
    accounts = _select_accounts(cfg.accounts, args.account)

    runner_triage = CodexRunner(repo_root=cfg.repo_root, provider=cfg.llm.provider, model=cfg.llm.triage_model)
    runner_reply = CodexRunner(repo_root=cfg.repo_root, provider=cfg.llm.provider, model=cfg.llm.reply_model)

    if args.cmd == "init":
        rows = []
        for a in accounts:
            logger.info("Initialising %s (%s)", a.email, a.label)
            res = init_account(cfg, a, runner_reply)
            rows.append(res)
        md = "# init report\n\n" + "\n".join([f"- **{r['account']}**: sender_stats={r['sender_stats']}, tone_contacts={r['tone_contacts']}" for r in rows]) + "\n"
        report_path = _write_report(cfg.repo_root, "init", md)
        print(f"Report: {report_path}")
        return

    if args.cmd == "run":
        rows = []
        for a in accounts:
            logger.info("Running triage for %s (%s)", a.email, a.label)
            res = run_for_account(cfg, a, runner_triage, runner_reply)
            rows.append(res)
        md_lines = ["# run report", ""]
        for r in rows:
            md_lines.append(f"- **{r['account']}**: processed={r.get('processed')}, drafts={r.get('drafts')}, tasks={r.get('tasks')}, informational={r.get('informational')}, summary_sent={r.get('summary_sent')}")
        md_lines.append("")
        report_path = _write_report(cfg.repo_root, "run", "\n".join(md_lines))
        print(f"Report: {report_path}")
        return
