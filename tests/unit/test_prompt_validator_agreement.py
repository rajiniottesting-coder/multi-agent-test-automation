"""Whatever the prompt tells Agent 2 to do, the validator must permit.

WHAT HAPPENED, TWICE
    A helper was added to BasePage for acting on ONE member of a family, the
    generation prompt was updated to recommend it, and the validator's list of
    sanctioned family consumers was not. Agent 2 followed the instruction
    exactly and every attempt was rejected:

        SomePage.click_in_row() is called with self.sel(<a family key>), but
        that key is listed under multi_match ...

    The repair loop cannot recover from this. Its feedback says "use a legal
    path", the prompt says the path it just used IS the legal one, and the two
    disagree - so four attempts burn and the story fails with no pull request.
    Nothing had changed in the app; the framework was arguing with itself.

    The first time it was click_nth. The second time click_in_row and
    row_containing. Both were caught by a human reading a failed run, which is
    the expensive way to find a contradiction between two files that are
    supposed to agree by construction.
"""
import ast
import re
from pathlib import Path

import pytest

from validators.method_resolution_validator import (
    _FAMILY_CONSUMERS,
    _FAMILY_READERS,
)

_PROJECT = Path(__file__).resolve().parents[2]
_PROMPT = _PROJECT / "prompts" / "agent2_coder_generate.md"
_SANCTIONED = _FAMILY_CONSUMERS | _FAMILY_READERS


def _helpers_the_prompt_shows_on_a_family() -> set:
    """BasePage helpers the prompt demonstrates being called with self.sel().

    Read from the prompt's own code samples, so the check tracks whatever the
    prompt actually says rather than a list someone has to remember to update.
    """
    text = _PROMPT.read_text(encoding="utf-8")
    found = set()
    for line in text.splitlines():
        # a recommended call, not a "NEVER write this" counter-example
        if "rejected" in line or "never" in line.lower():
            continue
        for m in re.finditer(r"self\.(\w+)\(\s*self\.sel\(", line):
            found.add(m.group(1))
    return found


def test_every_helper_the_prompt_recommends_is_sanctioned():
    """The guard that would have caught both incidents before the run."""
    recommended = _helpers_the_prompt_shows_on_a_family()
    assert recommended, "no self.<helper>(self.sel(...)) samples found in the prompt"

    # Only helpers that touch a FAMILY need sanctioning; a single-element call
    # such as fill(self.sel("search_input")) is legal without being listed.
    family_samples = {
        h for h in recommended
        if h in _SANCTIONED or h in {"click_in_row", "row_containing", "click_nth"}
    }
    unsanctioned = family_samples - _SANCTIONED
    assert not unsanctioned, (
        f"the prompt tells Agent 2 to use {sorted(unsanctioned)} on a family "
        f"key, but the validator does not sanction them. Agent 2 will follow "
        f"the instruction and be rejected every time, and the repair loop "
        f"cannot resolve a contradiction between the prompt and the gate."
    )


@pytest.mark.parametrize("helper", sorted(_FAMILY_CONSUMERS))
def test_every_sanctioned_consumer_exists_on_base_page(helper):
    """The mirror: sanctioning a method BasePage does not define would let
    generated code past the gate and fail with AttributeError at run time."""
    source = (_PROJECT / "pages" / "base_page.py").read_text(encoding="utf-8")
    names = {
        n.name for n in ast.walk(ast.parse(source))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert helper in names, (
        f"{helper!r} is sanctioned as a family consumer but BasePage does not "
        f"define it - generated code calling it would pass the gate and then "
        f"raise AttributeError."
    )


@pytest.mark.parametrize("helper", sorted(_FAMILY_READERS))
def test_every_sanctioned_reader_exists_on_base_page(helper):
    source = (_PROJECT / "pages" / "base_page.py").read_text(encoding="utf-8")
    names = {
        n.name for n in ast.walk(ast.parse(source))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert helper in names, f"{helper!r} is sanctioned but BasePage lacks it"


# ─────────────────────────────────────────────────────────────────────────
# FOUR sources tell Agent 2 how to touch a family. All four must agree.
#
# Sanctioning click_in_row in the validator fixed the rejection but left three
# other voices saying something else:
#
#   the prompt              "use click_in_row(...)"
#   the validator's list    click_in_row is legal          <- the only one fixed
#   the repair message      "read it with one of: exists, get_all_texts, ..."
#   the inventory note      "never click, fill or assert on them"
#
# Two of the four actively forbade the thing the prompt requires - and the
# repair message is what Agent 2 reads AFTER a failure, so the one voice with
# the last word was steering it away from the answer. The inventory note is
# worse still: the crawler regenerates it, so every future app would have
# started with the same contradiction.
#
# A guard on one source is not a guard on the rule.
# ─────────────────────────────────────────────────────────────────────────

_ONE_MEMBER_HELPER = "click_in_row"


def test_the_repair_message_names_the_click_path():
    """The message Agent 2 reads after a rejection. Listing only the readers
    left it no way to CLICK one member, which is the commonest reason to touch
    a family at all."""
    source = (_PROJECT / "validators" / "method_resolution_validator.py").read_text(
        encoding="utf-8")
    start = source.index("multi_match on inventory page")
    block = source[start:start + 2500]
    assert _ONE_MEMBER_HELPER in block, (
        "the multi_match rejection message does not mention "
        f"{_ONE_MEMBER_HELPER}(), so a model told 'you may not click this' is "
        "given only read-only alternatives and cannot satisfy the scenario."
    )


def test_the_crawler_note_template_does_not_forbid_the_sanctioned_path():
    """The note is REGENERATED for every app, so a contradiction here ships to
    every future project rather than just this one."""
    source = (_PROJECT / "inventory_tools" / "introspect.py").read_text(encoding="utf-8")
    # Only the INSTRUCTION forms - "never click, fill ..." addressed at the
    # reader. Prose such as "a crawler never clicks" describes the tool's
    # reach and is not guidance about what generated code may do.
    for match in re.finditer(r"never click, fill[^\"]*", source):
        window = source[max(0, match.start() - 500):match.end() + 300]
        assert _ONE_MEMBER_HELPER in window, (
            f"a generated multi_match note forbids clicking without naming "
            f"{_ONE_MEMBER_HELPER}() as the sanctioned way to act on one "
            f"member: {match.group(0)[:80]!r}"
        )


def test_committed_inventory_notes_do_not_forbid_it_either():
    import json
    from core.app_context import AppContext

    path = AppContext.load().inventory_path()
    if not path.is_file():
        pytest.skip("no inventory configured yet")
    data = json.loads(path.read_text(encoding="utf-8"))
    for name, page in (data.get("pages") or {}).items():
        note = page.get("multi_match_note") or ""
        if "never click" in note:
            assert _ONE_MEMBER_HELPER in note, (
                f"{name}.multi_match_note forbids clicking without naming "
                f"{_ONE_MEMBER_HELPER}(). Agent 2 reads this note and the "
                f"prompt, and they disagree."
            )