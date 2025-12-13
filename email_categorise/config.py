from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import toml  # type: ignore[import]


@dataclass
class AuthConfig:
    auth_mode: str = "application"  # application | delegated
    token_cache_path: str = "./data/msal_token_cache.bin"


@dataclass
class AzureConfig:
    client_id: str
    tenant_id: str
    authority_base: str = "https://login.microsoftonline.com"
    client_secret_env: str = "MS_GRAPH_CLIENT_SECRET"
    delegated_scopes: List[str] = field(default_factory=lambda: ["Mail.ReadWrite", "Mail.Send"])


@dataclass
class TriageConfig:
    lookback_days_initial: int = 60
    lookback_days_incremental: int = 3
    max_messages_per_run: int = 40
    tone_profile_lookback_days: int = 120
    draft_replies: bool = False
    create_tasks: bool = False
    send_summary_email: bool = False
    log_to_file: bool = True
    summary_email_to: Optional[str] = None
    summary_email_from_account: Optional[str] = None


@dataclass
class LLMConfig:
    provider: str = "codex"  # codex | codex-oss
    triage_model: str = "gpt-4.1-mini"
    reply_model: str = "gpt-4.1"


@dataclass
class AccountConfig:
    email: str
    label: str
    tenant_id: Optional[str] = None  # overrides azure.tenant_id if set


@dataclass
class AppConfig:
    auth: AuthConfig
    azure: AzureConfig
    triage: TriageConfig
    llm: LLMConfig
    accounts: List[AccountConfig]
    repo_root: Path


def load_config(path: str | Path) -> AppConfig:
    cfg_path = Path(path).expanduser().resolve()
    repo_root = cfg_path.parent
    raw = toml.load(str(cfg_path))

    auth_raw = raw.get("auth", {})
    azure_raw = raw.get("azure", {})
    triage_raw = raw.get("triage", {})
    llm_raw = raw.get("llm", {})
    accounts_raw = raw.get("accounts", [])

    auth = AuthConfig(
        auth_mode=str(auth_raw.get("auth_mode", "application")),
        token_cache_path=str(auth_raw.get("token_cache_path", "./data/msal_token_cache.bin")),
    )

    azure = AzureConfig(
        client_id=str(azure_raw["client_id"]),
        tenant_id=str(azure_raw.get("tenant_id", "organizations")),
        authority_base=str(azure_raw.get("authority_base", "https://login.microsoftonline.com")),
        client_secret_env=str(azure_raw.get("client_secret_env", "MS_GRAPH_CLIENT_SECRET")),
        delegated_scopes=[str(s) for s in azure_raw.get("delegated_scopes", ["Mail.ReadWrite", "Mail.Send"])],
    )

    triage = TriageConfig(
        lookback_days_initial=int(triage_raw.get("lookback_days_initial", 60)),
        lookback_days_incremental=int(triage_raw.get("lookback_days_incremental", 3)),
        max_messages_per_run=int(triage_raw.get("max_messages_per_run", 40)),
        tone_profile_lookback_days=int(triage_raw.get("tone_profile_lookback_days", 120)),
        draft_replies=bool(triage_raw.get("draft_replies", False)),
        create_tasks=bool(triage_raw.get("create_tasks", False)),
        send_summary_email=bool(triage_raw.get("send_summary_email", False)),
        log_to_file=bool(triage_raw.get("log_to_file", True)),
        summary_email_to=triage_raw.get("summary_email_to"),
        summary_email_from_account=triage_raw.get("summary_email_from_account"),
    )

    llm = LLMConfig(
        provider=str(llm_raw.get("provider", "codex")),
        triage_model=str(llm_raw.get("triage_model", "gpt-4.1-mini")),
        reply_model=str(llm_raw.get("reply_model", "gpt-4.1")),
    )

    accounts: List[AccountConfig] = []
    for a in accounts_raw:
        email = str(a["email"])
        label = str(a.get("label", email))
        tenant_id = a.get("tenant_id")
        accounts.append(AccountConfig(email=email, label=label, tenant_id=str(tenant_id) if tenant_id else None))

    return AppConfig(auth=auth, azure=azure, triage=triage, llm=llm, accounts=accounts, repo_root=repo_root)
