from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    # Map category/priority name -> desired read state after processing.
    # Values: True = mark read, False = leave unread.
    priority_read_state: Dict[str, bool] = field(
        default_factory=lambda: {
            "default": False,  # keep unread unless told otherwise
            "Urgent": False,
            "Priority 1": False,
            "Priority 2": False,
            "Priority 3": False,
            "Marketing": True,
            "Informational": False,
            "Complete": True,
            "Possibly Complete": True,
        }
    )


@dataclass
class LLMConfig:
    provider: str = "codex"  # codex | codex-oss
    triage_model: str = "gpt-4.1-mini"
    reply_model: str = "gpt-4.1"


@dataclass
class AzureOverrides:
    client_id: Optional[str] = None
    tenant_id: Optional[str] = None
    authority_base: Optional[str] = None
    client_secret_env: Optional[str] = None
    delegated_scopes: Optional[List[str]] = None


@dataclass
class TriageOverrides:
    draft_replies: Optional[bool] = None
    create_tasks: Optional[bool] = None
    send_summary_email: Optional[bool] = None
    log_to_file: Optional[bool] = None
    summary_email_to: Optional[str] = None
    summary_email_from_account: Optional[str] = None
    priority_read_state: Optional[Dict[str, bool]] = None


@dataclass
class AccountConfig:
    email: str
    label: str
    tenant_id: Optional[str] = None  # overrides azure.tenant_id if set
    azure_overrides: AzureOverrides = field(default_factory=AzureOverrides)
    triage_overrides: TriageOverrides = field(default_factory=TriageOverrides)


@dataclass
class AppConfig:
    auth: AuthConfig
    azure: AzureConfig
    triage: TriageConfig
    llm: LLMConfig
    accounts: List[AccountConfig]
    repo_root: Path

    def azure_for_account(self, account: AccountConfig) -> AzureConfig:
        base = replace(self.azure)
        ov = account.azure_overrides
        if ov.client_id:
            base.client_id = ov.client_id
        if ov.authority_base:
            base.authority_base = ov.authority_base
        if ov.client_secret_env:
            base.client_secret_env = ov.client_secret_env
        if ov.delegated_scopes:
            base.delegated_scopes = ov.delegated_scopes
        # tenant selection: override precedence account.azure_overrides > account.tenant_id > base default
        if ov.tenant_id:
            base.tenant_id = ov.tenant_id
        elif account.tenant_id:
            base.tenant_id = account.tenant_id
        return base

    def triage_for_account(self, account: AccountConfig) -> TriageConfig:
        base = replace(self.triage)
        ov = account.triage_overrides
        if ov.draft_replies is not None:
            base.draft_replies = ov.draft_replies
        if ov.create_tasks is not None:
            base.create_tasks = ov.create_tasks
        if ov.send_summary_email is not None:
            base.send_summary_email = ov.send_summary_email
        if ov.log_to_file is not None:
            base.log_to_file = ov.log_to_file
        if ov.summary_email_to is not None:
            base.summary_email_to = ov.summary_email_to
        if ov.summary_email_from_account is not None:
            base.summary_email_from_account = ov.summary_email_from_account
        if ov.priority_read_state:
            merged = dict(base.priority_read_state)
            merged.update(ov.priority_read_state)
            base.priority_read_state = merged
        return base


def _resolve_config_path(path: str | Path) -> Path:
    """
    Resolve a user-supplied config path with new defaults:
    - allow pointing at a directory (uses config.toml inside)
    - fall back to config/<file> if only a filename is provided
    """
    supplied = Path(path).expanduser()
    cfg_path = supplied / "config.toml" if supplied.is_dir() else supplied

    if cfg_path.exists():
        return cfg_path.resolve()

    # Fallback: look inside repo-level config/ for the same filename
    repo_config = Path(__file__).resolve().parent.parent / "config" / cfg_path.name
    if repo_config.exists():
        return repo_config.resolve()

    raise FileNotFoundError(f"Config file not found: {cfg_path}")


def _detect_repo_root(cfg_path: Path) -> Path:
    """
    Determine repo root whether config lives in repo/ or repo/config/.
    """
    if (cfg_path.parent / "email_categorise").exists():
        return cfg_path.parent
    if (cfg_path.parent.parent / "email_categorise").exists():
        return cfg_path.parent.parent
    return cfg_path.parent


def _parse_priority_read_state(raw_map: Mapping[str, object] | None) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    if not raw_map:
        return out
    for k, v in raw_map.items():
        key = str(k)
        if isinstance(v, bool):
            out[key] = v
        else:
            out[key] = str(v).strip().lower() in {"1", "true", "yes", "read"}
    return out


def load_config(path: str | Path) -> AppConfig:
    cfg_path = _resolve_config_path(path)
    repo_root = _detect_repo_root(cfg_path)
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

    triage_default_read_state = TriageConfig().priority_read_state
    triage_read_state = {**triage_default_read_state, **_parse_priority_read_state(triage_raw.get("priority_read_state"))}

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
        priority_read_state=triage_read_state,
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

        azure_ov_raw = a.get("azure_overrides", {})
        triage_ov_raw = a.get("triage_overrides", {})

        azure_ov = AzureOverrides(
            client_id=azure_ov_raw.get("client_id"),
            tenant_id=azure_ov_raw.get("tenant_id"),
            authority_base=azure_ov_raw.get("authority_base"),
            client_secret_env=azure_ov_raw.get("client_secret_env"),
            delegated_scopes=[str(s) for s in azure_ov_raw.get("delegated_scopes")] if azure_ov_raw.get("delegated_scopes") else None,
        )

        triage_ov = TriageOverrides(
            draft_replies=triage_ov_raw.get("draft_replies"),
            create_tasks=triage_ov_raw.get("create_tasks"),
            send_summary_email=triage_ov_raw.get("send_summary_email"),
            log_to_file=triage_ov_raw.get("log_to_file"),
            summary_email_to=triage_ov_raw.get("summary_email_to"),
            summary_email_from_account=triage_ov_raw.get("summary_email_from_account"),
            priority_read_state=_parse_priority_read_state(triage_ov_raw.get("priority_read_state")),
        )

        accounts.append(
            AccountConfig(
                email=email,
                label=label,
                tenant_id=str(tenant_id) if tenant_id else None,
                azure_overrides=azure_ov,
                triage_overrides=triage_ov,
            )
        )

    return AppConfig(auth=auth, azure=azure, triage=triage, llm=llm, accounts=accounts, repo_root=repo_root)
