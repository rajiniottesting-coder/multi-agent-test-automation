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

# =========================================================================
# A HELPER THE PROMPT RECOMMENDS MUST EXIST ON BasePage
#
# The same contradiction in its simplest form. The prompt now tells Agent 2
# to end a navigating method with confirm_arrival(); if that name is ever
# renamed or dropped from BasePage, every generated page object calls a
# method that is not there and the whole suite errors on import.
#
# Read from the prompt rather than a hardcoded list, so this tracks whatever
# the prompt actually says.
# =========================================================================

def _helpers_the_prompt_recommends() -> set:
    """Every self.<helper>(...) the prompt shows in a sample it endorses.

    Arguments included. The first version matched only `self.x()` with EMPTY
    parentheses, so `self.wait_for_count(self.sel(...), n)` was never checked -
    and wait_for_count was then added to BasePage and to the prompt without
    being added to the validator's sanctioned family readers. The gate rejected
    the helper its own prompt had just recommended, and a repair loop burned
    four attempts on it.

    A helper is only as sanctioned as the narrowest check that sees it.
    """
    text = _PROMPT.read_text(encoding="utf-8")
    found = set()
    for line in text.splitlines():
        if "rejected" in line or "never" in line.lower():
            continue
        for m in re.finditer(r"self\.(\w+)\s*\(", line):
            found.add(m.group(1))
    return found


# Backwards-compatible alias for the narrower original.
_bare_helpers_the_prompt_recommends = _helpers_the_prompt_recommends


def test_every_bare_helper_the_prompt_recommends_exists_on_base_page():
    source = (_PROJECT / "pages" / "base_page.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined = {
        node.name
        for cls in tree.body if isinstance(cls, ast.ClassDef)
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    # Methods the page object DEFINES rather than inherits are not BasePage's.
    generated_locally = {"is_loaded"}

    for helper in _helpers_the_prompt_recommends() - generated_locally:
        assert helper in defined, (
            f"the generation prompt shows self.{helper}(), but BasePage has no "
            f"{helper}(). Agent 2 will follow the prompt and every generated "
            f"page object will fail on the call."
        )

# =========================================================================
# THE REFERENCE PAGE OBJECT MUST PASS THE RULES IT TEACHES
#
# The reference trio is what Agent 2 is shown as the gold standard. It defined
# `open(base_url)`. Agent 2 copied the convention onto a listing page, added
# `open_product()` beside it, and the duplicate-method check rejected the pair
# - the page's own noun is dropped, so `open_product` reduces to `open`.
#
# The framework taught a name and then punished it. The remedy it printed
# ("delete the other") would have broken the tests, because the two methods do
# different things.
#
# Whatever the reference teaches, Agent 2 will write. So the reference goes
# through the same validators as generated code.
# =========================================================================

def test_the_reference_page_object_passes_the_page_object_validators():
    from types import SimpleNamespace

    from validators.method_resolution_validator import (
        validate_no_duplicate_page_object_methods,
        validate_page_method_names_are_specific,
        validate_predicates_wait,
    )

    import yaml
    config = yaml.safe_load(
        (_PROJECT / "config" / "config.yaml").read_text(encoding="utf-8"))
    rel = ((config.get("app_under_test") or {}).get("reference_files") or {}
           ).get("page_object")
    assert rel, "config.yaml names no reference page object"

    path = _PROJECT / rel
    assert path.exists(), f"the reference page object {rel} is missing"

    reference = [SimpleNamespace(file_path=rel,
                                 content=path.read_text(encoding="utf-8"))]

    for check in (validate_no_duplicate_page_object_methods,
                  validate_page_method_names_are_specific,
                  validate_predicates_wait):
        errors = check(reference)
        assert not errors, (
            f"{rel} is the example Agent 2 copies, and it fails "
            f"{check.__name__}:\n  " + "\n  ".join(errors) + "\n"
            f"Whatever the reference teaches, the generated code will do - and "
            f"the gate will then reject it for following the example."
        )


def test_every_committed_page_object_passes_the_naming_rule():
    """The second home. A gate only guards what passes through it, and a
    hand-edited page object never passes through the generation gate."""
    from types import SimpleNamespace

    from validators.method_resolution_validator import (
        validate_page_method_names_are_specific,
    )

    files = [
        SimpleNamespace(file_path=f"pages/{f.name}",
                        content=f.read_text(encoding="utf-8"))
        for f in sorted((_PROJECT / "pages").glob("*_page.py"))
        if f.name != "base_page.py"
    ]
    if not files:
        pytest.skip("no page objects committed yet")

    assert not validate_page_method_names_are_specific(files)

def test_a_helper_the_prompt_recommends_for_a_family_is_sanctioned_for_one():
    """The first entry in the failure history, repeated.

    A multi_match key may only reach a helper listed in _FAMILY_READERS or
    _FAMILY_CONSUMERS. wait_for_count() was added to BasePage, recommended in
    the prompt for counting rows - which are always a family - and left out of
    both sets. The gate then rejected the prompt's own advice, and no rewrite
    could satisfy both voices.
    """
    from validators.method_resolution_validator import (
        _FAMILY_CONSUMERS,
        _FAMILY_READERS,
    )

    sanctioned = _FAMILY_READERS | _FAMILY_CONSUMERS

    assert "wait_for_count" in sanctioned, (
        "wait_for_count counts a family by definition - rows, cards, results. "
        "Leaving it out of the sanctioned sets is what made the gate reject "
        "the prompt's own recommendation."
    )


def test_every_committed_page_object_passes_the_predicate_rule():
    """The second home. validate_predicates_wait runs at the GENERATION gate,
    so it never sees a page object that was hand-edited or merged - and the
    committed nav page object violated it while the whole suite stayed green."""
    from types import SimpleNamespace

    from validators.method_resolution_validator import validate_predicates_wait

    files = [
        SimpleNamespace(file_path=f"pages/{f.name}",
                        content=f.read_text(encoding="utf-8"))
        for f in sorted((_PROJECT / "pages").glob("*_page.py"))
        if f.name != "base_page.py"
    ]
    if not files:
        pytest.skip("no page objects committed yet")

    errors = validate_predicates_wait(files, _PROJECT)
    assert not errors, (
        "a committed page object fails the rule generated code is held to:\n  "
        + "\n  ".join(errors)
    )