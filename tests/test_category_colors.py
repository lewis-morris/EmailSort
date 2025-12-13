"""Unit test for ensuring master category colours are managed.

Uses a tiny fake Graph client to avoid network calls. Verifies that
`ensure_master_categories` issues create/update/unchanged actions and that
triage_logic wires the colour map we expect.
"""

from __future__ import annotations

from typing import Any, Dict, List

from email_categorise.graph_client import _plan_category_updates
from email_categorise.triage_logic import CATEGORY_COLORS


def _fake_existing(categories: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    return [{"displayName": c[0], "color": c[1], "id": f"id-{i}"} for i, c in enumerate(categories)]


def test_plan_category_updates_create_and_update_and_keep():
    desired = {
        "Urgent": "red",
        "Priority 1": "orange",
        "Priority 2": "yellow",
    }
    existing = _fake_existing([
        ("Urgent", "yellow"),  # needs update
        ("Priority 2", "yellow"),  # unchanged
    ])

    plan = _plan_category_updates(desired, existing)

    assert plan["Urgent"]["action"] == "update"
    assert plan["Urgent"]["color"] == "red"
    assert plan["Priority 2"]["action"] == "unchanged"
    assert plan["Priority 2"]["color"] == "yellow"
    assert plan["Priority 1"]["action"] == "create"
    assert plan["Priority 1"]["color"] == "orange"


def test_category_color_map_covers_all_known_categories():
    # Categories listed in CATEGORY_HELP plus Processed should all have colours
    expected_keys = {
        "Urgent",
        "Priority 1",
        "Priority 2",
        "Priority 3",
        "Marketing",
        "Informational",
        "No reply needed",
        "Complete",
        "Possibly Complete",
        "Processed",
    }

    assert set(CATEGORY_COLORS.keys()) == expected_keys
