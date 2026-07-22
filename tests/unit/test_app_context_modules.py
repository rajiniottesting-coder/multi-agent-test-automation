"""
Unit tests for Phase-2 Tier-2 app-context changes:

  2.1 — module-wise app context (load_app_context_block)
  2.6 — inventory JSON minification (load_page_inventory_json)

No Jira / LLM / network. Pure file-loading and JSON logic, driven through
temporary prompt folders and inventory files.
"""
import json
import textwrap

import pytest

import agents.agent1_analyst as analyst
from agents.app_context import AppContext


# ═══════════════════════════════════════════════════════════════════
# 2.1 — module-wise app context
#
# load_app_context_block(components) chooses its layout from the filesystem:
#   • no prompts/app_context/ folder  → single prompts/app_context.md (legacy)
#   • folder present                  → core.md + per-component files
# We point PROMPTS_DIR at a tmp folder per test to exercise each branch.
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def prompts_dir(tmp_path, monkeypatch):
    """Redirect the analyst's PROMPTS_DIR to a temp folder for the test."""
    monkeypatch.setattr(analyst, "PROMPTS_DIR", tmp_path)
    return tmp_path


# ---- Layout 1: single file (backward compatibility) ----

def test_single_file_used_when_no_folder(prompts_dir):
    (prompts_dir / "app_context.md").write_text("SINGLE FILE CONTEXT", encoding="utf-8")
    out = analyst.load_app_context_block()
    assert out == "SINGLE FILE CONTEXT"


def test_single_file_ignores_components_arg(prompts_dir):
    """Passing components must not change single-file behaviour."""
    (prompts_dir / "app_context.md").write_text("SINGLE", encoding="utf-8")
    assert analyst.load_app_context_block(["Orders", "Billing"]) == "SINGLE"


def test_missing_everything_returns_empty(prompts_dir):
    # No file, no folder → empty string (prompt still runs), not an exception.
    assert analyst.load_app_context_block() == ""


# ---- Layout 2: module-wise ----

@pytest.fixture
def module_folder(prompts_dir):
    folder = prompts_dir / "app_context"
    folder.mkdir()
    (folder / "core.md").write_text("CORE", encoding="utf-8")
    (folder / "orders.md").write_text("ORDERS", encoding="utf-8")
    (folder / "billing.md").write_text("BILLING", encoding="utf-8")
    (folder / "user_management.md").write_text("USERS", encoding="utf-8")
    return folder


def test_core_always_injected(module_folder):
    out = analyst.load_app_context_block(["Orders"])
    assert "CORE" in out
    assert "ORDERS" in out
    assert "BILLING" not in out       # unrelated module excluded
    assert "USERS" not in out


def test_multiple_components(module_folder):
    out = analyst.load_app_context_block(["Orders", "Billing"])
    assert "CORE" in out and "ORDERS" in out and "BILLING" in out
    assert "USERS" not in out


def test_component_name_normalisation(module_folder):
    """'User Management' → user_management.md (case + space insensitive)."""
    out = analyst.load_app_context_block(["User Management"])
    assert "USERS" in out
    assert "CORE" in out


def test_hyphen_normalisation(module_folder):
    (module_folder / "order_history.md").write_text("HISTORY", encoding="utf-8")
    out = analyst.load_app_context_block(["order-history"])
    assert "HISTORY" in out


def test_no_components_injects_all_modules(module_folder):
    """Safe default: a story with no components gets every module."""
    out = analyst.load_app_context_block([])
    for token in ("CORE", "ORDERS", "BILLING", "USERS"):
        assert token in out


def test_none_components_injects_all_modules(module_folder):
    out = analyst.load_app_context_block(None)
    for token in ("CORE", "ORDERS", "BILLING", "USERS"):
        assert token in out


def test_unknown_component_falls_back_to_all(module_folder):
    """A component with no matching file → inject all (never silently empty)."""
    out = analyst.load_app_context_block(["NonexistentModule"])
    for token in ("CORE", "ORDERS", "BILLING", "USERS"):
        assert token in out


def test_partial_match_injects_only_matched(module_folder):
    """One known + one unknown → inject core + the known one only."""
    out = analyst.load_app_context_block(["Orders", "Ghost"])
    assert "CORE" in out and "ORDERS" in out
    assert "BILLING" not in out and "USERS" not in out


def test_core_optional(prompts_dir):
    """Folder without core.md still works — just injects the matched modules."""
    folder = prompts_dir / "app_context"
    folder.mkdir()
    (folder / "orders.md").write_text("ORDERS", encoding="utf-8")
    out = analyst.load_app_context_block(["Orders"])
    assert out == "ORDERS"


def test_empty_folder_returns_empty(prompts_dir):
    (prompts_dir / "app_context").mkdir()
    assert analyst.load_app_context_block(["Orders"]) == ""


def test_modules_separated_by_blank_line(module_folder):
    out = analyst.load_app_context_block(["Orders", "Billing"])
    # Blocks joined with a blank line so the LLM sees them as distinct sections.
    assert "\n\n" in out


# ═══════════════════════════════════════════════════════════════════
# 2.6 — inventory minification
# ═══════════════════════════════════════════════════════════════════

def _ctx_with_inventory(tmp_path, monkeypatch, content: str):
    """Build an AppContext whose inventory_path points at a temp file."""
    inv = tmp_path / "inv.json"
    inv.write_text(content, encoding="utf-8")
    ctx = AppContext.__new__(AppContext)          # bypass load(); we only need the method
    monkeypatch.setattr(type(ctx), "inventory_path", lambda self: inv)
    return ctx


def test_minify_produces_single_line_valid_json(tmp_path, monkeypatch):
    pretty = json.dumps({"pages": {"login": {"url": "/", "elements": {"u": "#user"}}}}, indent=2)
    ctx = _ctx_with_inventory(tmp_path, monkeypatch, pretty)
    out = ctx.load_page_inventory_json()
    assert "\n" not in out                        # single line
    assert json.loads(out) == json.loads(pretty)  # same data
    assert len(out) <= len(pretty)                # not larger


def test_minify_preserves_colons_in_string_values(tmp_path, monkeypatch):
    """A ': ' inside a value (e.g. an error string) must survive intact."""
    data = {"pages": {"login": {"elements_notes": {"err": "Error: bad input"}}}}
    ctx = _ctx_with_inventory(tmp_path, monkeypatch, json.dumps(data, indent=2))
    out = ctx.load_page_inventory_json()
    assert json.loads(out)["pages"]["login"]["elements_notes"]["err"] == "Error: bad input"


def test_minify_preserves_unicode(tmp_path, monkeypatch):
    data = {"pages": {"p": {"note": "café — naïve"}}}
    ctx = _ctx_with_inventory(tmp_path, monkeypatch, json.dumps(data))
    out = ctx.load_page_inventory_json()
    assert json.loads(out)["pages"]["p"]["note"] == "café — naïve"


def test_malformed_json_falls_back_to_raw(tmp_path, monkeypatch):
    """Invalid JSON → return raw text unchanged, no exception (pre-2.6 behaviour)."""
    bad = "{ not: valid json ]"
    ctx = _ctx_with_inventory(tmp_path, monkeypatch, bad)
    assert ctx.load_page_inventory_json() == bad


def test_missing_inventory_still_raises(tmp_path, monkeypatch):
    """A MISSING file must still raise FileNotFoundError — only PARSE errors fall back."""
    missing = tmp_path / "nope.json"
    ctx = AppContext.__new__(AppContext)
    monkeypatch.setattr(type(ctx), "inventory_path", lambda self: missing)
    with pytest.raises(FileNotFoundError):
        ctx.load_page_inventory_json()