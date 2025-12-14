from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterable, Optional

import msal  # type: ignore[import]
from msal_extensions import FilePersistence, PersistedTokenCache  # type: ignore[import]

from .config import AzureConfig
from .utils import ensure_dir, load_env_file, save_json

logger = logging.getLogger("email_categorise.auth")

RESERVED_SCOPES = {"openid", "profile", "offline_access"}


def _build_cache(cache_path: Path) -> PersistedTokenCache:
    persistence = FilePersistence(str(cache_path))
    cache = PersistedTokenCache(persistence)
    return cache


def _authority(azure: AzureConfig, tenant_id: str) -> str:
    base = azure.authority_base.rstrip("/")
    return f"{base}/{tenant_id}"


def record_login_event(
    repo_root: Path,
    account_email: str,
    auth_mode: str,
    tenant_id: str,
    run_id: Optional[str],
) -> Path:
    """
    Persist non-sensitive auth/session metadata for audit/rollback awareness.
    Tokens remain only in MSAL cache.
    """
    login_dir = ensure_dir(repo_root / "login")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = account_email.replace("@", "_at_").replace("/", "_")
    rid = run_id or "norun"
    path = login_dir / f"{safe}_{stamp}_{rid}.json"
    save_json(
        path,
        {
            "account": account_email,
            "auth_mode": auth_mode,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "agent_type": "email_categorise",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    return path


def build_public_client(
    azure: AzureConfig, cache_path: Path, tenant_id: str
) -> msal.PublicClientApplication:
    cache_path = cache_path.expanduser()
    ensure_dir(cache_path.parent)
    cache = _build_cache(cache_path)
    return msal.PublicClientApplication(
        client_id=azure.client_id,
        authority=_authority(azure, tenant_id),
        token_cache=cache,
    )


def build_confidential_client(
    azure: AzureConfig, cache_path: Path, tenant_id: str
) -> msal.ConfidentialClientApplication:
    cache_path = cache_path.expanduser()
    ensure_dir(cache_path.parent)
    cache = _build_cache(cache_path)
    load_env_file()
    client_secret = os.environ.get(azure.client_secret_env)
    if not client_secret:
        raise RuntimeError(
            f"Missing client secret env var: {azure.client_secret_env}. "
            "Set it before running (do not put secrets in config.toml)."
        )
    return msal.ConfidentialClientApplication(
        client_id=azure.client_id,
        authority=_authority(azure, tenant_id),
        client_credential=client_secret,
        token_cache=cache,
    )


def acquire_delegated_token(
    app: msal.PublicClientApplication,
    scopes: Iterable[str],
    username: str,
) -> dict | None:
    scopes_clean = []
    for s in scopes:
        if s.lower() in RESERVED_SCOPES:
            logger.warning("Ignoring reserved scope in config: %s", s)
            continue
        scopes_clean.append(s)

    accounts = app.get_accounts(username=username)
    result: dict | None = None
    if accounts:
        logger.debug("Attempting silent token acquisition for %s", username)
        result = app.acquire_token_silent(list(scopes_clean), account=accounts[0])

    if not result:
        logger.info(
            "No suitable cached token for %s, launching interactive login...", username
        )
        result = app.acquire_token_interactive(
            scopes=list(scopes_clean),
            login_hint=username,
            prompt="select_account",
        )

    if not result or "access_token" not in result:
        logger.error(
            "Failed to acquire delegated token for %s: %s",
            username,
            (result or {}).get("error_description"),
        )
        return None
    return result


def acquire_application_token(
    app: msal.ConfidentialClientApplication,
) -> dict | None:
    # Uses the Graph .default scope set, representing app permissions granted in the portal.
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if not result or "access_token" not in result:
        logger.error(
            "Failed to acquire application token: %s",
            (result or {}).get("error_description"),
        )
        return None
    return result
