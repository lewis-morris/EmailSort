"""
Manual integration checks against the primary mailbox.

Prerequisites (do not commit secrets):
- `config.toml` populated with a primary account and application-auth settings.
- `MS_GRAPH_CLIENT_SECRET` exported in the shell.

Notes:
- Tests exercise live Graph endpoints; they are marked so you opt-in before running.
- Never run in CI; these expect real tenant data and will read/modify categories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

import pytest

from email_categorise import auth
from email_categorise.config import load_config
from email_categorise.graph_client import GraphClient
from email_categorise.triage_logic import CATEGORY_COLORS, _build_followup_flag
from email_categorise.utils import load_env_file, utc_now


pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def app_config():
    load_env_file()
    cfg_path = Path("config.toml")
    if not cfg_path.exists():
        pytest.skip("config.toml missing; create from config.example.toml with primary account settings")
    return load_config(cfg_path)


@pytest.fixture(scope="session")
def primary_account(app_config):
    if not app_config.accounts:
        pytest.skip("No accounts configured in config.toml")
    return app_config.accounts[0]


@pytest.fixture(scope="session")
def graph(app_config, primary_account):
    if app_config.auth.auth_mode != "application":
        pytest.skip("Integration tests expect application auth for unattended runs")

    client = auth.build_confidential_client(
        azure=app_config.azure,
        cache_path=Path(app_config.auth.token_cache_path),
        tenant_id=primary_account.tenant_id or app_config.azure.tenant_id,
    )
    token = auth.acquire_application_token(client)
    if not token:
        pytest.skip("Unable to acquire application token (check client secret/env and app permissions)")
    access_token = token["access_token"]
    return GraphClient(access_token=access_token, user=primary_account.email)


@pytest.fixture(scope="session")
def random_subject() -> str:
    return f"integration-self-{uuid4()}"


@pytest.fixture(scope="session")
def self_message(graph: GraphClient, primary_account, random_subject) -> Dict:
    msg = graph.send_mail_and_wait(
        subject=random_subject,
        html_body="<p>Integration self-test. Safe to ignore.</p>",
        to_address=primary_account.email,
        timeout_seconds=120,
        poll_interval=6,
    )
    if msg is None:
        pytest.skip("Timed out waiting for self-sent message to appear in Inbox")
    return msg


def test_master_categories_coloured(graph: GraphClient):
    """Ensure master categories exist with our colour palette."""
    results = graph.ensure_master_categories(CATEGORY_COLORS)
    refreshed = graph.list_master_categories()
    by_name = {c["displayName"]: c for c in refreshed}
    for name, color in CATEGORY_COLORS.items():
        assert name in by_name
        assert by_name[name]["color"] == color
        assert results[name] in {"create", "update", "unchanged"}


def test_tags_message_processed_and_flag_today(graph: GraphClient, self_message: Dict):
    """Apply Processed + IntegrationTest and flag Today to a freshly sent mail."""
    new_categories = set(self_message.get("categories") or [])
    new_categories.update({"Processed", "IntegrationTest"})
    flag_obj = _build_followup_flag("Today")

    graph.update_message(self_message["id"], {"categories": sorted(new_categories), "flag": flag_obj})

    refreshed = graph._get(f"{graph._user_root}/messages/{self_message['id']}")
    assert "Processed" in refreshed.get("categories", [])
    assert "IntegrationTest" in refreshed.get("categories", [])
    assert refreshed.get("flag", {}).get("flagStatus") == "flagged"


def test_creates_draft_reply(graph: GraphClient, self_message: Dict):
    """Create a draft reply to confirm reply flow works."""
    draft_id = graph.create_draft_reply(
        message_id=self_message["id"],
        reply_body_html="<p>Integration reply test — safe to ignore.</p>",
    )
    assert draft_id, "Expected draft id from createReply"
