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
    # such as fill(self.sel("filter_input")) is legal without being listed.
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

def test_the_validator_reads_the_family_lists_from_base_page():
    """One source of truth, not two copies kept in step by hand.

    The validator used to hold its own copy of "which helpers may take a
    multi_match key". Twice, a family-aware helper was added to BasePage and
    recommended in the generation prompt with the validator never told - so the
    gate rejected the prompt's own advice, and Agent 2 spent its repair budget
    moving one call between lines because no rewrite satisfied both voices.

    The lists now live in pages/base_page.py beside the helpers, and this
    checks the validator actually reads them rather than falling back to a
    stale copy.
    """
    import ast

    from validators.method_resolution_validator import (
        _FAMILY_CONSUMERS,
        _FAMILY_READERS,
    )

    tree = ast.parse((_PROJECT / "pages" / "base_page.py").read_text(encoding="utf-8"))
    declared = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in ("FAMILY_READERS", "FAMILY_CONSUMERS"):
                call = node.value
                declared[target.id] = frozenset(
                    e.value for e in call.args[0].elts
                    if isinstance(e, ast.Constant))

    assert declared, "pages/base_page.py declares no FAMILY_* lists"
    assert _FAMILY_READERS == declared["FAMILY_READERS"], (
        "the validator's family readers differ from what BasePage declares - "
        "it is reading a stale copy"
    )
    assert _FAMILY_CONSUMERS == declared["FAMILY_CONSUMERS"]


def test_every_sanctioned_helper_actually_exists_on_base_page():
    """A name in the list that BasePage does not define sends the model to a
    method that is not there. This is the same failure in the other
    direction."""
    import ast

    from validators.method_resolution_validator import (
        _FAMILY_CONSUMERS,
        _FAMILY_READERS,
    )

    tree = ast.parse((_PROJECT / "pages" / "base_page.py").read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body if isinstance(cls, ast.ClassDef)
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    for helper in sorted(_FAMILY_READERS | _FAMILY_CONSUMERS):
        assert helper in defined, (
            f"{helper!r} is sanctioned for a multi_match key but BasePage does "
            f"not define it"
        )


def test_a_family_helper_the_prompt_recommends_is_sanctioned():
    """The rule this test used to be, restored.

    It had degenerated into `assert "wait_for_count" in sanctioned` - a fact
    about one helper rather than a rule - after the general form false-flagged
    a single-element helper. Narrowing it removed the only thing that would
    have caught the NEXT one, and the next one arrived: wait_for_row, added to
    BasePage and the prompt, unsanctioned, rejected at the gate.

    The general form works now because the prompt writes a family argument as a
    placeholder - `<the row family>` - so a recommendation involving a family
    is identifiable without guessing.
    """
    import re

    from validators.method_resolution_validator import (
        _FAMILY_CONSUMERS,
        _FAMILY_READERS,
    )

    sanctioned = _FAMILY_READERS | _FAMILY_CONSUMERS
    text = _PROMPT.read_text(encoding="utf-8")

    recommended = set()
    for line in text.splitlines():
        if "rejected" in line.lower() or "never" in line.lower():
            continue
        for match in re.finditer(r"self\.(\w+)\(|\.(\w+)\(", line):
            helper = match.group(1) or match.group(2)
            if "family" in line.lower() or "row family" in line:
                recommended.add(helper)

    unsanctioned = {h for h in recommended
                    if h not in sanctioned and h not in ("sel", "format")}
    assert not unsanctioned, (
        f"the generation prompt recommends {sorted(unsanctioned)} with a "
        f"family argument, but none of them is in FAMILY_READERS or "
        f"FAMILY_CONSUMERS. Agent 2 will follow the prompt and the selector "
        f"gate will reject it - the two voices disagree and no rewrite "
        f"satisfies both."
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


# =========================================================================
# THE PROMPT MUST NOT FORBID WHAT THE REFERENCE DOES
#
# The generation prompt said "Absence is its own call, NEVER a negated
# presence check", and the reference step definitions assert
#
#     assert not nav_page.is_logged_in(), "Unexpectedly logged in"
#
# which is a negated presence check. Agent 2 is shown both. It obeyed the
# prompt, invented a WAITING logged-out probe to assert absence with, and the
# review flagged it for contradicting the reference - correctly.
#
# The rule's reasoning was sound and its scope was not: a presence probe can
# only answer "no" by timing out IF IT WAITS. The reference's probe does not
# wait, so negating it is free.
#
# Four sources carried this rule and only one of them was right. That is the
# first entry in the failure history, and it keeps happening because prose
# rules are checked by reading and reading is where it slips.
#
# This check is textual and narrow on purpose: it looks for a pattern the
# reference actually uses and asserts the prompt does not call that pattern
# rejected. It cannot judge prose in general - but it can notice when the
# example under a "rejected" heading is something the reference ships.
# =========================================================================

def _reference_step_def_path():
    import yaml

    config = yaml.safe_load(
        (_PROJECT / "config" / "config.yaml").read_text(encoding="utf-8"))
    rel = ((config.get("app_under_test") or {}).get("reference_files") or {}
           ).get("step_def")
    return (_PROJECT / rel) if rel else None


def test_the_prompt_does_not_reject_a_pattern_the_reference_uses():
    """Shapes the reference relies on must not appear under a rejected heading."""
    import re

    path = _reference_step_def_path()
    if not path or not path.is_file():
        pytest.skip("no reference step definitions in this checkout")

    # Normalise line endings before any regex. The first version of this
    # check used `\n` terminators against a CRLF file, matched nothing, and
    # passed while the contradiction it was written for was present.
    reference = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    prompt = _PROMPT.read_text(encoding="utf-8").replace("\r\n", "\n")

    # The shapes worth checking are assertion forms - that is where the
    # reference teaches a convention and the prompt can contradict it.
    shapes = {
        "negated non-waiting probe": (
            re.compile(r"assert\s+not\s+\w+\.is_\w+\("),
            # The prompt writes examples with PLACEHOLDERS - `is_<state>()`,
            # not a literal method name - so the pattern has to tolerate
            # angle brackets. Without that it matched nothing and the guard
            # could not fail, which is the same as not having it.
            re.compile(r"assert\s+not\s+<?\w+>?\.is_[\w<>]+\("),
        ),
    }

    for name, (in_reference, in_prompt) in shapes.items():
        if not in_reference.search(reference):
            continue                       # the reference does not use it

        # Find every "rejected" example block in the prompt and check the
        # shape is not one of them.
        for block in re.findall(r"#\s*rejected[^\n]*\n((?:[^\n]*\n)+?)\n", prompt):
            assert not in_prompt.search(block), (
                f"the generation prompt marks the {name!r} shape as rejected, "
                f"but {path.name} uses it. Agent 2 is shown both and will obey "
                f"one of them; the review then flags whichever it chose. "
                f"Rejected block:\n    " + block.strip().replace("\n", "\n    ")
            )


def test_the_check_can_tell_the_two_probe_kinds_apart():
    """Break the thing the guard guards.

    The whole rule turns on waiting versus non-waiting. If the prompt stopped
    drawing that distinction, this would be worth failing over.
    """
    prompt = _PROMPT.read_text(encoding="utf-8")
    lowered = " ".join(prompt.split()).lower()

    assert "non-waiting" in lowered, (
        "the prompt no longer distinguishes waiting from non-waiting probes - "
        "that distinction is the entire content of the absence rule"
    )
    assert "wait_for_row" in prompt, "the waiting form for absence must be named"


# =========================================================================
# THE PROMPT'S FINAL CHECK MUST MATCH THE VALIDATOR'S
#
# The prompt gave Agent 2 a mandatory self-check before submitting, and it
# counted PHRASES:
#
#     "De-duplicate phrases that differ only in concrete data"
#     "For each Gherkin phrase, locate its matching decorator"
#
# The validator counts (KEYWORD, phrase) PAIRS, because pytest-bdd does -
# verified by running it: a `@given` does not satisfy a `When` step, it raises
# StepDefinitionNotFoundError at collection and every scenario in the file
# fails.
#
# A feature using one phrase under two keywords therefore needs two
# decorators. The model, following its own mandated check, counted the phrase
# once, found one decorator, and concluded the file was complete. The gate
# then rejected it, the repair loop fed the rejection back, and the model
# re-ran the same check and reached the same conclusion - four times, then the
# story was abandoned.
#
# It was not a weak model. It was following the instructions it was given.
# =========================================================================

def test_the_prompt_counts_keyword_and_phrase_not_phrase_alone():
    """The self-check the prompt mandates must agree with the gate that runs
    after it, or the model's own verification tells it to submit."""
    prompt = _PROMPT.read_text(encoding="utf-8").replace("\r\n", "\n")
    plain = " ".join(prompt.split())

    assert "(KEYWORD, phrase)" in prompt, (
        "the final check counts phrases, not keyword+phrase pairs - so a "
        "phrase used under two keywords passes the model's own check and "
        "fails the gate"
    )
    assert "do not de-duplicate across keywords" in plain.lower(), (
        "without this the model collapses `Given X` and `When X` into one"
    )


def test_the_prompt_shows_how_to_satisfy_two_keywords():
    """Naming the rule is not enough - the answer looks like a duplicate, and
    a model avoiding duplicates will not reach for it unaided."""
    prompt = _PROMPT.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert "@given(" in prompt and "@when(" in prompt
    stacked = [
        block for block in prompt.split("\n\n")
        if "@given(" in block and "@when(" in block
        and block.index("@given(") < block.index("@when(")
    ]
    assert stacked, (
        "the prompt never shows two keyword decorators stacked on one "
        "function, which is the fix for a phrase used under two keywords"
    )


def test_the_validator_accepts_the_form_the_prompt_teaches():
    """The other half of prompt/validator agreement, and the one that has
    bitten this project most: the gate must accept what the prompt recommends.
    """
    import textwrap
    from types import SimpleNamespace

    from validators.gherkin_analyzer import (
        validate_no_duplicate_step_definitions,
        validate_step_definitions_complete,
    )

    feature = SimpleNamespace(file_path="features/x.feature",
                              content=textwrap.dedent('''
        Feature: F

          Scenario: A
            Given I am on a page
            Then something happens

          Scenario: B
            When I am on a page
            Then something happens
    '''))
    stacked = SimpleNamespace(file_path="tests/step_defs/test_x.py",
                              content=textwrap.dedent('''
        from pytest_bdd import scenarios, given, when, then

        scenarios("x.feature")


        @given("I am on a page")
        @when("I am on a page")
        def on_a_page():
            pass


        @then("something happens")
        def something():
            pass
    '''))

    assert validate_step_definitions_complete([feature, stacked]) == [], (
        "the coverage check must see BOTH decorators on the stacked function"
    )
    assert validate_no_duplicate_step_definitions([stacked], _PROJECT) == [], (
        "the same phrase under DIFFERENT keywords is not a duplicate - the "
        "duplicate rule is about the same keyword, where the second "
        "declaration silently shadows the first"
    )


# =========================================================================
# EVERY REJECTION MUST LEAVE A LEGAL MOVE
#
# A page object was asked "does this list have anything in it?" and had
# nothing it was allowed to write:
#
#     get_count(family) > 0   -> waiting-predicate error
#     exists(family)          -> the same defect, waved through by name
#     is_showing(family)      -> selector error, family key
#     wait_for_count(fam, n)  -> needs an exact number the question has none of
#
# Three rejections and no accepted alternative is not a rule, it is a trap.
# One run spent every repair attempt cycling between them - 34% of its cost -
# and the story was abandoned.
#
# And the framework was rejecting names it MANDATES: both clearing methods in
# `_starting_state.establishing_calls` are verb phrases, and the reader-naming
# check read their verbs as fields they had failed to return.
# =========================================================================

def _page_object(body: str, inventory_page: str):
    import textwrap
    from types import SimpleNamespace
    return SimpleNamespace(
        file_path="pages/widget_page.py",
        content=("from pages.base_page import BasePage\n\n\n"
                 "class WidgetPage(BasePage):\n"
                 f'    INVENTORY_PAGE = "{inventory_page}"\n\n')
                + textwrap.indent(textwrap.dedent(body).strip("\n"), "    ") + "\n")


def _a_family_key():
    """(page name, a multi_match key on it) discovered from the inventory."""
    import json

    import yaml

    config = yaml.safe_load((_PROJECT / "config" / "config.yaml").read_text(encoding="utf-8"))
    rel = (config.get("app_under_test") or {}).get("inventory_file")
    inventory = json.loads((_PROJECT / rel).read_text(encoding="utf-8"))
    for name, entry in (inventory.get("pages") or {}).items():
        for key in (entry.get("multi_match") or []):
            return name, key
    return None, None


def test_asking_whether_a_family_has_any_members_has_a_legal_answer():
    """The question that had none."""
    from validators.method_resolution_validator import (
        validate_page_object_methods,
        validate_page_object_selectors,
    )

    page, key = _a_family_key()
    if not key:
        pytest.skip("this inventory declares no multi_match family")

    racy = [f'self.get_count(self.sel("{key}")) > 0',
            f'self.exists(self.sel("{key}"))',
            f'self.is_showing(self.sel("{key}"))']
    for expression in racy:
        obj = _page_object(f"def has_items(self) -> bool:\n    return {expression}\n", page)
        assert (validate_page_object_methods([obj])
                + validate_page_object_selectors([obj], _PROJECT)), (
            f"{expression} reads the page once or uses a family key - it must "
            f"be rejected, or the racy form ships"
        )

    legal = _page_object(
        f'def has_items(self) -> bool:\n'
        f'    self.wait_for_any(self.sel("{key}"))\n'
        f'    return True\n', page)
    errors = (validate_page_object_methods([legal])
              + validate_page_object_selectors([legal], _PROJECT))
    assert not errors, (
        "every way of asking 'are there any' is rejected. Three rejections and "
        "no accepted alternative is a trap, not a rule - the repair loop can "
        "only cycle:\n  " + "\n  ".join(errors)
    )


def test_the_clearing_calls_the_inventory_mandates_pass_the_validators():
    """The framework must not reject the names it asks for.

    `_starting_state.establishing_calls` is what the persistent-state error
    tells a scenario to use. Those names are verb phrases, and the
    reader-naming check read their verbs as fields they had failed to return:
    `clear_the_basket()` was reported as promising "empty" and "cart". A run
    spent all four repair attempts on it.

    Built to touch a family on the PERSISTENT page - the one those calls
    clear - because a family whose words happen to overlap the method name
    never triggers the rule, and a guard that misses is worse than none.
    """
    import json

    import yaml

    from validators.method_resolution_validator import (
        _promised_nouns,
        validate_readers_return_what_they_name,
    )

    config = yaml.safe_load((_PROJECT / "config" / "config.yaml").read_text(encoding="utf-8"))
    rel = (config.get("app_under_test") or {}).get("inventory_file")
    inventory = json.loads((_PROJECT / rel).read_text(encoding="utf-8"))
    calls = ((inventory.get("_starting_state") or {}).get("establishing_calls") or [])
    if not calls:
        pytest.skip("this inventory mandates no clearing calls")

    for name in calls:
        promised = _promised_nouns(name)

        # Find a family on a persistent page whose key words do NOT cover the
        # promised words - otherwise the rule cannot fire and this proves
        # nothing.
        page = key = None
        for candidate, entry in (inventory.get("pages") or {}).items():
            if not entry.get("persistent_state"):
                continue
            for family in (entry.get("multi_match") or []):
                if not promised <= set(family.split("_")):
                    page, key = candidate, family
                    break
            if key:
                break
        if not key:
            continue

        obj = _page_object(
            f'def {name}(self) -> None:\n'
            f'    labels = self.get_all_texts(self.sel("{key}"))\n'
            f'    for _ in labels:\n'
            f'        self.click_nth(self.sel("{key}"), 0)\n', page)

        errors = validate_readers_return_what_they_name([obj], _PROJECT)
        assert not errors, (
            f"the inventory mandates {name}() and the validators reject it - "
            f"following the persistent-state advice fails a different gate:\n  "
            + "\n  ".join(errors)
        )


def test_a_genuinely_misnamed_reader_is_still_caught():
    """Break the thing the guard guards.

    Exempting actions must not exempt readers. A method that RETURNS whole-row
    text under a field's name is the defect this check exists for.
    """
    from validators.method_resolution_validator import (
        validate_readers_return_what_they_name)

    page, key = _a_family_key()
    if not key:
        pytest.skip("this inventory declares no multi_match family")

    obj = _page_object(
        f'def get_item_price(self) -> str:\n'
        f'    return self.get_text(self.sel("{key}"))\n', page)
    assert validate_readers_return_what_they_name([obj], _PROJECT), (
        "a reader named for one field that returns the whole row must still "
        "be rejected"
    )


# =========================================================================
# A RULE THE GATE ENFORCES MUST BE TAUGHT BEFORE THE GATE RUNS
#
# `wait_for_any` was added to BasePage, sanctioned as a family reader, and
# named in the rejection message - and never mentioned in the generation
# prompt. So the model could only satisfy the waiting-predicate rule by
# FAILING first and reading the repair feedback.
#
# That is a whole extra LLM call, every run, for a rule the prompt could have
# stated in five lines. Repairs are for mistakes, not for delivering
# instructions that could have arrived with the brief.
#
# The signal is a repair that succeeds on the first attempt: the model knew
# what to do the moment it was told, which means telling it earlier costs
# nothing and saves a call.
# =========================================================================

def test_the_prompt_teaches_every_probe_the_gate_will_reject():
    """Each non-waiting probe, and the helper offered in its place, must
    appear in the generation prompt - not only in the rejection message."""
    from validators.method_resolution_validator import _NON_WAITING_PROBES

    prompt = _PROMPT.read_text(encoding="utf-8")

    for probe, remedy in _NON_WAITING_PROBES.items():
        assert probe in prompt, (
            f"the gate rejects {probe}() and the prompt never mentions it - "
            f"the model can only learn this by failing first"
        )
        # The remedy string may name several helpers; every identifier in it
        # that looks like a helper has to be teachable.
        import re
        for helper in set(re.findall(r"\b(wait_[a-z_]+|is_showing)\b", remedy)):
            assert helper in prompt, (
                f"{probe}() is rejected in favour of {helper}(), which the "
                f"prompt never names. Every run pays a repair call to be told "
                f"something the brief could have carried."
            )