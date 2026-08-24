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
from core.app_context import AppContext


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


def test_unknown_component_injects_all_MODULES(module_folder):
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

# ─────────────────────────────────────────────────────────────────────────
# If the context claims data is test-owned, it must also say whether it is
# CLEAN
#
# One app's context said an account's data "cannot be seen or changed by anyone
# else", and that was read as "starts empty". It does not: the state survived
# logout and survived the run. Two CI failures came from it - a collection
# expected to hold one item held two, and one expected to be empty after a
# removal still showed a leftover from a run that had died mid-scenario.
#
# The test is conditional BY DESIGN. Plenty of applications have no persistent
# per-account state, and forcing every context module to carry a warning about
# one would be this framework telling a new project what its app is like. The
# check fires only where the context itself raises the subject.
# ─────────────────────────────────────────────────────────────────────────

def test_a_test_owned_data_claim_also_states_whether_it_starts_clean():
    from pathlib import Path

    folder = Path(__file__).resolve().parents[2] / "prompts" / "app_context"
    if not folder.is_dir():
        pytest.skip("no app_context modules in this checkout")

    for module in sorted(folder.glob("*.md")):
        body = module.read_text(encoding="utf-8")
        # Markdown wraps at the column, so a phrase can be split by a newline.
        # Collapse whitespace before matching, or the check depends on where
        # the author happened to break the line.
        lowered = " ".join(body.lower().split())
        claims_ownership = (
            "test-owned" in lowered
            or "cannot be seen or changed by anyone else" in lowered
        )
        if not claims_ownership:
            continue

        assert "not the same as empty" in lowered, (
            f"{module.name} tells the model that data is private to the test's "
            f"own account without saying whether that account starts CLEAN. "
            f"Private and empty are different claims, and a model reading only "
            f"the first will assume a fresh start and write an absolute "
            f"assertion that fails on the second run. If this application "
            f"really does start clean every time, say so explicitly."
        )
        assert "relativ" in lowered, (
            f"{module.name} raises the starting-state problem without naming "
            f"the fallback: a relative assertion - that the thing this test "
            f"added is present - is true whatever the account started with."
        )


# =========================================================================
# A CONTEXT PARAGRAPH MUST NOT END MID-SENTENCE
#
# The starting-state warning the check above looks for was once added to a
# context module by pasting it into the MIDDLE of an existing sentence. What
# the model read was the first half of one instruction, then the warning,
# then the second half - and the two halves said the opposite of the warning
# between them. Agent 2 followed the half that suited it.
#
# The check above passed throughout, because it asks whether the warning is
# PRESENT and it was: present, and buried inside a broken sentence arguing
# against it.
#
# So this checks STRUCTURE, not vocabulary. A prose paragraph that ends
# without terminal punctuation has had something inserted into it, and
# whatever was inserted is now sitting inside a sentence it did not belong
# to. That is detectable without knowing anything about the application,
# which is the only kind of check allowed to live in this file.
# =========================================================================

_TERMINAL = (".", "!", "?", ":", ";", '"', "'", ")", "`")


def _prose_paragraphs(text: str):
    """Blank-line-separated blocks that are prose, not markup.

    Skipped: headings, tables, lists, block quotes, fenced code, ASCII flow
    diagrams (an arrow is not a sentence) and prompt placeholders.
    """
    blocks, current, in_fence = [], [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            current.append(line)
            continue
        if not line.strip() and not in_fence:
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)

    for block in blocks:
        joined = "\n".join(block)
        if block[0].lstrip().startswith(("#", "|", "-", "*", ">", "```")):
            continue
        if any(token in joined for token in ("```", "\u2192", "->", "{")):
            continue
        yield block


def test_a_context_paragraph_never_ends_mid_sentence():
    from pathlib import Path

    folder = Path(__file__).resolve().parents[2] / "prompts" / "app_context"
    if not folder.is_dir():
        pytest.skip("no app_context modules in this checkout")

    for module in sorted(folder.glob("*.md")):
        for block in _prose_paragraphs(module.read_text(encoding="utf-8")):
            last = block[-1].rstrip()
            assert last.endswith(_TERMINAL), (
                f"{module.name}: a paragraph ends mid-sentence:\n"
                f"    ...{last[-70:]!r}\n"
                f"Something has been inserted into this sentence, which means "
                f"the model is reading the inserted text as part of a "
                f"different instruction. Close the sentence, then add the new "
                f"paragraph after it."
            )


def test_the_paragraph_check_catches_a_real_splice():
    """Break the thing the guard guards.

    The exact shape that shipped: a paragraph pasted between the two halves of
    a sentence. If this stops being detected, the check above has stopped
    doing anything.
    """
    spliced = (
        "A sentence that starts here, states something the model is meant\n"
        "to act on, and is interrupted before it reaches the\n"
        "\n"
        "An inserted warning that says the opposite of the sentence it landed\n"
        "in the middle of.\n"
        "\n"
        "qualification that would have changed its meaning.\n"
    )
    unterminated = [
        block for block in _prose_paragraphs(spliced)
        if not block[-1].rstrip().endswith(_TERMINAL)
    ]
    assert unterminated, "the splice shape must be detectable"

    clean = (
        "A sentence that starts here and reaches its own full stop.\n"
        "\n"
        "A warning that stands on its own, after a closed sentence.\n"
    )
    assert not [
        block for block in _prose_paragraphs(clean)
        if not block[-1].rstrip().endswith(_TERMINAL)
    ], "well-formed prose must not be flagged"


# =========================================================================
# A context module must not ship the same paragraph twice
#
# WHAT HAPPENED
#   core.md carried the "PRIVATE IS NOT THE SAME AS EMPTY" section THREE
#   times - three rewrites of one instruction, each appended instead of
#   replacing the last. Two commits built it up: one left two copies, the
#   next left three. 45 of 148 lines were duplication.
#
#   It is not free. Every copy is paid for in every Agent 1, 2 and 3 call,
#   and three near-identical passages that differ slightly read to a model
#   as three instructions rather than one emphasised instruction - the
#   preference tables in those three copies did not say the same thing.
#
#   Nothing caught it because nothing was looking. A duplicated paragraph
#   is not malformed: it parses, it ends in a full stop, and it says
#   something true.
#
# This checks STRUCTURE, not vocabulary - the same rule the splice check
# above follows. Repetition is detectable without knowing anything about
# the application.
# =========================================================================


def _normalised(block) -> str:
    """One paragraph as comparable text: whitespace and case flattened.

    Reflowing a paragraph to a different line width, or fixing its casing,
    does not make it a different paragraph.
    """
    return " ".join(" ".join(block).split()).lower()


def _duplicate_paragraphs(text: str, min_words: int = 25):
    """Prose paragraphs appearing more than once, longest first.

    Short blocks are ignored: a one-line lead-in such as "In order of
    preference:" is legitimately repeated, and flagging it would train the
    reader to ignore this check.
    """
    seen: dict = {}
    for block in _prose_paragraphs(text):
        norm = _normalised(block)
        if len(norm.split()) < min_words:
            continue
        seen.setdefault(norm, 0)
        seen[norm] += 1
    return sorted(
        (norm for norm, n in seen.items() if n > 1),
        key=len,
        reverse=True,
    )


def test_no_context_module_repeats_a_paragraph():
    from pathlib import Path

    folder = Path(__file__).resolve().parents[2] / "prompts" / "app_context"
    if not folder.is_dir():
        pytest.skip("no app_context modules in this checkout")

    for module in sorted(folder.glob("*.md")):
        dupes = _duplicate_paragraphs(module.read_text(encoding="utf-8"))
        assert not dupes, (
            f"{module.name}: a paragraph appears more than once:\n"
            f"    {dupes[0][:110]!r}...\n"
            f"An edit has been APPENDED where it should have REPLACED. Every "
            f"copy is re-sent in every agent call, and near-identical copies "
            f"that differ slightly read as separate instructions rather than "
            f"one. Delete the older copies."
        )


def test_the_duplicate_check_catches_the_shape_that_shipped():
    """Break the thing the guard guards.

    The exact shape from core.md: one instruction, rewritten and appended,
    so the copies are near-identical rather than byte-identical.
    """
    para = (
        "That account's state survives logout and survives the end of the "
        "run, so a scenario that added something and then failed before "
        "removing it leaves that item behind for the next run to find.\n"
    )
    doubled = para + "\n" + para
    assert _duplicate_paragraphs(doubled), "an exact repeat must be detected"

    reflowed = " ".join(para.split())
    assert _duplicate_paragraphs(para + "\n" + reflowed + "\n"), (
        "a repeat that has only been re-wrapped is still a repeat"
    )

    assert not _duplicate_paragraphs(para), "a single copy must not be flagged"

    short = "In order of preference:\n"
    assert not _duplicate_paragraphs(short + "\n" + short), (
        "a short repeated lead-in is legitimate and must not be flagged"
    )


# =========================================================================
# THE CONTEXT MUST NOT OFFER A ROUTE THE INVENTORY HAS CLOSED
#
# `_starting_state.establishing_calls` was emptied - the collection is
# cleared by hand BEFORE a run, not by a generated step during one - and a
# context module went on telling the model to write that step, naming a
# method the inventory no longer sanctions.
#
# The validator's remedy and the context module then said different things,
# and the model follows whichever it read last. Four sources, one right, is
# the first entry in this project's failure history.
# =========================================================================

def test_no_context_module_offers_an_establishing_call_the_inventory_denies():
    import json
    import re

    import yaml

    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "config" / "config.yaml").read_text(encoding="utf-8"))
    rel = (config.get("app_under_test") or {}).get("inventory_file")
    inventory = json.loads((root / rel).read_text(encoding="utf-8"))

    sanctioned = set(((inventory.get("_starting_state") or {})
                      .get("establishing_calls") or []))

    for module in sorted((root / "prompts" / "app_context").glob("*.md")):
        text = module.read_text(encoding="utf-8")
        # Any method the prose tells the model to CALL for a clean start.
        for named in re.findall(r"`(\w+)\(\)`", text):
            if named in sanctioned:
                continue
            window = text[max(0, text.index(f"`{named}()`") - 200):
                          text.index(f"`{named}()`") + 200].lower()
            if "clear" in window or "empty the" in window or "establishing_calls" in window:
                raise AssertionError(
                    f"{module.name} tells the model to call {named}() to "
                    f"establish a clean start, but the inventory sanctions "
                    f"{sorted(sanctioned) or 'nothing'}. Following the context "
                    f"module fails the gate; following the gate contradicts "
                    f"the context module."
                )