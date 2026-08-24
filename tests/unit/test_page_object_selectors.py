"""Page objects resolve selectors from the app inventory, not from literals.

APP-AGNOSTIC BY CONSTRUCTION
---------------------------
These tests exercise the MECHANISM (BasePage.sel / page_url and the
no-literals rule), never a particular application. Pointing the framework at a
different app must not change a line here, so:

  - the sel()/page_url() tests build a SYNTHETIC inventory and a throwaway
    page object; they import no application page object and never read the
    real inventory
  - the no-literals scan walks whatever is in pages/ and cares only about the
    SHAPE of what it finds

Why the rule exists: the inventory is the single source of truth, and an agent
cannot hallucinate a selector it never writes. `self.sel("x")` is checkable
against the inventory; a literal `"input[name='x']"` is not.
"""
import ast
import json
import re
from pathlib import Path

import pytest

from pages.base_page import BasePage

PAGES_DIR = Path(__file__).resolve().parents[2] / "pages"

# A selector-looking literal: css, or one of Playwright's engine prefixes.
# A selector literal, wherever it appears. The original pattern required an
# `= "..."`, so it caught an ASSIGNMENT - `SELECTOR = "#id"` - and missed the
# commoner shape by far: the literal handed straight to a helper,
# `self.click("#id")`. One injected into a committed page object passed the
# entire suite. Matching the quoted string itself covers both, and both quote
# styles.
_SELECTOR_LITERAL = re.compile(
    r"""["'](?:\s*[.#\[]|(?:role|text|label|alt|title|placeholder)=)[^"']*["']"""
)


# A synthetic app. Deliberately nothing to do with the app under test.
_FAKE_INVENTORY = {
    "pages": {
        "widget_screen": {
            "url": "/widgets/list",
            "elements": {
                "search_box": "[data-test='search']",
                "submit_button": "role=button[name='Go']",
            },
        }
    }
}


@pytest.fixture
def fake_inventory(monkeypatch):
    """Point BasePage at a synthetic inventory for the duration of a test."""
    monkeypatch.setattr(BasePage, "_INVENTORY_CACHE", _FAKE_INVENTORY,
                        raising=False)
    yield
    monkeypatch.setattr(BasePage, "_INVENTORY_CACHE", None, raising=False)


class _WidgetPage(BasePage):
    INVENTORY_PAGE = "widget_screen"


class _UnwiredPage(BasePage):
    pass


# ── the mechanism ────────────────────────────────────────────

def test_sel_resolves_a_key_to_its_selector(fake_inventory):
    assert _WidgetPage.sel("search_box") == "[data-test='search']"
    assert _WidgetPage.sel("submit_button") == "role=button[name='Go']"


def test_page_url_comes_from_the_inventory(fake_inventory):
    assert _WidgetPage.page_url() == "/widgets/list"


def test_unknown_key_raises_and_lists_what_is_available(fake_inventory):
    """A silent None would mis-select; the error must be actionable."""
    with pytest.raises(KeyError) as exc:
        _WidgetPage.sel("no_such_element")
    msg = str(exc.value)
    assert "no_such_element" in msg
    assert "Available" in msg
    assert "search_box" in msg                    # names the real keys


def test_unknown_inventory_page_raises_and_lists_the_pages(fake_inventory):
    class _Wrong(BasePage):
        INVENTORY_PAGE = "no_such_page"
    with pytest.raises(KeyError, match="Available pages"):
        _Wrong.sel("anything")


def test_page_object_without_inventory_page_fails_clearly(fake_inventory):
    with pytest.raises(RuntimeError, match="INVENTORY_PAGE"):
        _UnwiredPage.sel("anything")
    with pytest.raises(RuntimeError, match="INVENTORY_PAGE"):
        _UnwiredPage.page_url()


# ── the rule, applied to whatever pages/ contains ────────────

def _page_object_files():
    return [f for f in sorted(PAGES_DIR.glob("*_page.py"))
            if f.name != "base_page.py"]


def test_no_page_object_contains_a_selector_literal():
    """The rule this whole design exists to enforce."""
    offenders = []
    for f in _page_object_files():
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'", "*")):
                continue
            if _SELECTOR_LITERAL.search(line):
                offenders.append(f"{f.name}:{i}: {stripped[:70]}")
    assert not offenders, (
        'selector literal(s) in a page object — use self.sel("<key>") and add '
        "the element to the app inventory:\n  " + "\n  ".join(offenders))


def test_every_page_object_declares_an_inventory_page():
    """Without it, sel() raises at runtime instead of at import."""
    missing = []
    for f in _page_object_files():
        src = f.read_text(encoding="utf-8")
        if "INVENTORY_PAGE" not in src:
            missing.append(f.name)
    assert not missing, (
        f"page object(s) with no INVENTORY_PAGE: {missing}. Set it to the key "
        f"of the page they implement in the app inventory.")


def test_every_sel_key_used_exists_in_the_real_inventory():
    """Whatever app is configured, every key a page object asks for must be in
    its inventory page. AST, not regex: a docstring showing self.sel("<key>")
    as an EXAMPLE is documentation, not a call."""
    cfg = (PAGES_DIR.parent / "config" / "config.yaml").read_text(encoding="utf-8")
    m = re.search(r'inventory_file:\s*"([^"]+)"', cfg)
    if not m:
        pytest.skip("no inventory_file configured")
    inv_path = PAGES_DIR.parent / m.group(1)
    if not inv_path.is_file():
        pytest.skip(f"inventory not present at {inv_path}")
    pages = json.loads(inv_path.read_text(encoding="utf-8")).get("pages") or {}

    problems = []
    for f in _page_object_files():
        src = f.read_text(encoding="utf-8")
        page_key = re.search(r'INVENTORY_PAGE\s*=\s*"([^"]+)"', src)
        if not page_key:
            continue
        page_key = page_key.group(1)
        if page_key not in pages:
            problems.append(f"{f.name}: INVENTORY_PAGE={page_key!r} not in inventory")
            continue
        elements = (pages[page_key].get("elements") or {})
        for node in ast.walk(ast.parse(src)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "sel"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                key = node.args[0].value
                if key not in elements:
                    problems.append(
                        f"{f.name}:{node.lineno}: sel({key!r}) not in "
                        f"inventory page {page_key!r}")
    assert not problems, "\n  " + "\n  ".join(problems)

def test_no_page_object_builds_locator_syntax_in_code():
    """Applied to whatever `pages/` contains, not to a fixture.

    The generation gate rejects `f"{self.sel('rows')} >> nth={i}"`, but a gate
    only guards what passes THROUGH it. These files are Agent 2's output and
    they live on disk: a regeneration, a hand-edit, or a merge that predates
    the rule can all reintroduce the pattern without the gate ever running.

    This is the check that makes the fix durable rather than a one-time
    cleanup - it fails the suite on whatever is actually committed.
    """
    offenders = []
    for f in _page_object_files():
        source = f.read_text(encoding="utf-8")
        # Docstrings legitimately SHOW the anti-pattern while teaching it, and
        # base_page.py sets that example. Ask the AST rather than guessing
        # from a line prefix, which only catches a line STARTING with a quote.
        doc_lines = set()
        try:
            for node in ast.walk(ast.parse(source)):
                if (isinstance(node, ast.Expr)
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, str)):
                    doc_lines.update(
                        range(node.lineno, (node.end_lineno or node.lineno) + 1))
        except SyntaxError:
            pass

        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'", "*")) or i in doc_lines:
                continue
            if ">> nth=" in line or ">>nth=" in line:
                offenders.append(f"{f.name}:{i}: {stripped[:70]}")

    assert not offenders, (
        "locator syntax built in code — use "
        'self.click_nth(self.sel("<key>"), index), and get the index from '
        "self.find_row_index_by_text(...) so the element is chosen by what it "
        "SAYS before it is reached by where it sits:\n  " + "\n  ".join(offenders))


# =====================================================================
# Folded in from test_selector_literal_agreement.py
#
# Two checks the generation gate should have made and didn't.
#
# WHAT HAPPENED
#     A page object shipped with two raw selector literals:
#
#         row = self.row_containing(self.sel("table_rows"), name)
#         return row.locator(".row-quantity").inner_text().strip()
#
#     The generation gate passed it. The committed-tree scan then failed the
#     build. Both checks exist to enforce the same rule, and the comment above
#     the generation-time pattern said so:
#
#         "Deliberately the SAME shape as tests/unit/test_page_object_selectors
#          .py — the two must agree, or generation passes and the unit gate
#          still fails."
#
#     They did not agree. The generation-time version required an ASSIGNMENT
#     (`= "..."`), so a literal handed straight to a call was invisible to it.
#     The exact failure its own comment predicted.
#
#     A comment asserting that two patterns agree is a wish. This file makes it
#     a test: both patterns are run against the same corpus and must return the
#     same verdict on every line.
#
# AND THE ONE NOBODY WAS CHECKING
#     The same review found `assert actual == quantity`, where the step
#     decorator parses `{quantity:d}` as an int and the page-object reader is
#     annotated `-> str`. `"2" == 2` is always False.
#
#     That is the worst shape a test can have: it does not error and it does not
#     flake. It fails every single run, including when the application is
#     perfectly correct — so the failure points at the app, and the app is fine.
#     Both halves are declared, so nothing has to be inferred.
# =====================================================================

import textwrap
from types import SimpleNamespace
from validators.method_resolution_validator import (
    _SELECTOR_LITERAL_RE,
    validate_page_object_selectors,
    validate_step_parameter_types,
)

_PROJECT = Path(__file__).resolve().parents[2]


def _page(body: str) -> SimpleNamespace:
    return SimpleNamespace(file_path="pages/widget_page.py", content=(
        "from pages.base_page import BasePage\n\n\n"
        "class WidgetPage(BasePage):\n"
        '    INVENTORY_PAGE = "widget"\n\n'
        + textwrap.indent(textwrap.dedent(body).strip("\n"), "    ") + "\n"
    ))


# ─────────────────────────────────────────────────────────────────────────
# The two literal patterns must agree, line for line
# ─────────────────────────────────────────────────────────────────────────

_CORPUS = [
    # (line, is_a_literal_selector)
    ('    return row.locator(".row-quantity").inner_text()', True),
    ('    return row.locator("#total").inner_text()', True),
    ('    self.click("[data-qa=submit]")', True),
    ('    LOGIN = ".login-form"', True),
    ("    cell = row.locator('.price')", True),
    ('    self.click(self.sel("add_button"))', False),
    ('    self.navigate(base_url + "/basket")', False),
    ('    return self.get_text(self.sel("total"))', False),
    ('    name = "a plain string"', False),
    ("    return self.sel('table_rows')", False),
]


def _unit_test_pattern():
    """The committed-tree scan's own pattern, read from its module."""
    import importlib
    mod = importlib.import_module("tests.unit.test_page_object_selectors")
    return mod._SELECTOR_LITERAL


@pytest.mark.parametrize("line,is_literal", _CORPUS)
def test_both_literal_patterns_reach_the_same_verdict(line, is_literal):
    gate = bool(_SELECTOR_LITERAL_RE.search(line))
    committed = bool(_unit_test_pattern().search(line))

    assert gate == committed, (
        f"the two selector-literal patterns disagree on {line.strip()!r}: "
        f"generation gate says {gate}, committed-tree scan says {committed}. "
        f"When the gate is the lenient one, the code ships and the build fails "
        f"afterwards - which is what happened."
    )
    assert gate == is_literal, (
        f"{line.strip()!r} should{'' if is_literal else ' not'} read as a "
        f"selector literal"
    )


def test_the_literal_that_shipped_is_now_rejected_at_generation():
    """Break the thing the guard guards: the exact two lines from the run."""
    errors = validate_page_object_selectors([_page('''
        def get_quantity(self, name: str) -> str:
            row = self.row_containing(self.sel("rows"), name)
            return row.locator(".row-quantity").inner_text().strip()
    ''')], _PROJECT)

    assert errors, "the generation gate still misses a literal on a chained locator"
    assert "row-quantity" in errors[0]


def test_inventory_keys_and_urls_are_not_mistaken_for_selectors():
    """The pattern got wider. If it got too wide, every correct page object
    would be rejected and the check would be turned off within a day.

    Only the LITERAL half is under test here - this page object names a page
    that is not in whatever inventory the repo is pointed at, and that is a
    different (correct) complaint.
    """
    errors = validate_page_object_selectors([_page('''
        def open_widget(self, base_url: str) -> None:
            self.navigate(base_url + "/widgets")

        def names(self):
            return self.get_all_texts(self.sel("widget_names"))
    ''')], _PROJECT)

    literals = [e for e in errors if "literal selector" in e]
    assert not literals, literals


# ─────────────────────────────────────────────────────────────────────────
# A parsed parameter compared against a mistyped reader
# ─────────────────────────────────────────────────────────────────────────

_READER = SimpleNamespace(file_path="pages/widget_page.py", content=textwrap.dedent('''
    from pages.base_page import BasePage


    class WidgetPage(BasePage):
        INVENTORY_PAGE = "widget"

        def get_quantity(self, name: str) -> str:
            return self.get_text(self.sel("quantity"))

        def get_row_count(self) -> int:
            return self.get_count(self.sel("rows"))
'''))


def _steps(body: str) -> SimpleNamespace:
    return SimpleNamespace(file_path="tests/step_defs/test_widget.py",
                           content=textwrap.dedent(body))


def test_an_int_parameter_against_a_str_reader_is_rejected():
    errors = validate_step_parameter_types([_READER, _steps('''
        @then(parsers.parse("the quantity should be {quantity:d}"))
        def assert_quantity(widget_page, name, quantity):
            actual = widget_page.get_quantity(name)
            assert actual == quantity
    ''')], _PROJECT)

    assert len(errors) == 1
    message = errors[0]
    assert "int" in message and "str" in message, "name both types"
    assert "ALWAYS False" in message, (
        "say that it fails even when the application is correct - that is the "
        "whole reason this one is worth catching statically"
    )


def test_the_same_bug_written_inline_is_rejected():
    assert validate_step_parameter_types([_READER, _steps('''
        @then(parsers.parse("the quantity should be {quantity:d}"))
        def assert_quantity(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == quantity
    ''')], _PROJECT)


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("body,why", [
    ('''
        @then(parsers.parse("the quantity should be {quantity:d}"))
        def assert_quantity(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == str(quantity)
    ''', "an explicit cast is the fix, and must not be flagged"),
    ('''
        @then(parsers.parse("the list holds {count:d} rows"))
        def assert_rows(widget_page, count):
            assert widget_page.get_row_count() == count
    ''', "int reader against int parameter is correct"),
    ('''
        @then(parsers.parse("the quantity should be {quantity}"))
        def assert_quantity(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == quantity
    ''', "an untyped placeholder is a string on both sides"),
    ('''
        @then(parsers.parse("row {n:d} is present"))
        def assert_present(widget_page, n, name):
            assert name in widget_page.get_names(), f"row {n} missing"
    ''', "membership is not an equality comparison"),
])
def test_correct_comparisons_are_left_alone(body, why):
    assert validate_step_parameter_types([_READER, _steps(body)], _PROJECT) == [], why


def test_an_unannotated_reader_is_not_guessed_at():
    """No return annotation means no declared type. Inferring one would produce
    the false positives that get a validator switched off."""
    unannotated = SimpleNamespace(file_path="pages/widget_page.py", content=textwrap.dedent('''
        class WidgetPage:
            def get_quantity(self, name):
                return "2"
    '''))
    assert validate_step_parameter_types([unannotated, _steps('''
        @then(parsers.parse("the quantity should be {quantity:d}"))
        def assert_quantity(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == quantity
    ''')], _PROJECT) == []


# =========================================================================
# A STEP MUST CHECK EVERYTHING ITS SENTENCE PROMISES
#
# Two shapes the reviewer kept finding, neither caught by any gate:
#
#     @then(parsers.parse('... with quantity {quantity:d}'))
#     def assert_holds(page, name, quantity):
#         assert page.has_item(name)          # quantity never read
#
#     assert page.get_result_count() >= 0     # a count is never negative
#
# Both produce a scenario that PASSES when it should not. That is the worse
# direction: a test that fails wrongly gets fixed, and a test that passes
# wrongly is trusted and stays in the suite reporting coverage the run never
# had.
#
# The step text is what the feature file claims is verified, so the sentence
# is the specification and the body has to meet it.
# =========================================================================

def _page_with_readers():
    import textwrap
    from types import SimpleNamespace
    return SimpleNamespace(file_path="pages/widget_page.py",
                           content=textwrap.dedent('''
        from pages.base_page import BasePage


        class WidgetPage(BasePage):
            INVENTORY_PAGE = "widget"

            def has_item(self, name: str) -> bool:
                return True

            def get_result_count(self) -> int:
                return 0
    '''))


def _step(body: str):
    import textwrap
    from types import SimpleNamespace
    return SimpleNamespace(file_path="tests/step_defs/test_widget.py",
                           content=textwrap.dedent(body))


def test_a_captured_value_the_body_ignores_is_rejected():
    from validators.method_resolution_validator import validate_step_parameter_types

    errors = validate_step_parameter_types([_page_with_readers(), _step('''
        @then(parsers.parse('the collection holds "{name}" with quantity {quantity:d}'))
        def assert_holds(widget_page, name, quantity):
            assert widget_page.has_item(name)
    ''')], _PROJECT)

    assert errors, "the sentence promises a quantity the body never reads"
    assert "quantity" in errors[0]
    assert "passes for every value" in errors[0], (
        "say what goes wrong - 'unused parameter' sounds like tidiness"
    )


def test_an_assertion_that_cannot_fail_is_rejected():
    from validators.method_resolution_validator import validate_step_parameter_types

    errors = validate_step_parameter_types([_page_with_readers(), _step('''
        @then("the search should not falsely match anything")
        def assert_no_match(widget_page):
            assert widget_page.get_result_count() >= 0
    ''')], _PROJECT)

    assert errors, "a count is never negative - this cannot fail"
    assert "cannot fail" in errors[0]


def test_the_correct_forms_are_left_alone():
    """Break the thing the guard guards.

    Rejecting every use of a count, or every parameter, would block the
    working forms and the check would be switched off within a day.
    """
    from validators.method_resolution_validator import validate_step_parameter_types

    for body in ('''
        @then(parsers.parse('the collection holds "{name}" with quantity {quantity:d}'))
        def assert_holds(widget_page, name, quantity):
            assert widget_page.get_quantity(name) == quantity
    ''', '''
        @then("the search should not falsely match anything")
        def assert_no_match(widget_page):
            assert widget_page.get_result_count() == 0
    ''', '''
        @then(parsers.parse('the collection holds "{name}"'))
        def assert_holds(widget_page, name):
            assert widget_page.has_item(name), f"missing {name}"
    '''):
        assert validate_step_parameter_types(
            [_page_with_readers(), _step(body)], _PROJECT) == [], body


def test_the_prompt_teaches_this_before_the_gate_enforces_it():
    """A rule the model can only learn by failing costs an LLM call a run."""
    prompt = (_PROJECT / "prompts" / "agent2_coder_generate.md").read_text(
        encoding="utf-8")
    plain = " ".join(prompt.split()).lower()

    assert "everything its sentence promises" in plain, (
        "the generation prompt never states this rule"
    )
    assert ">= 0" in prompt, "show the assertion that cannot fail"


def test_an_assertion_wrapped_in_a_tautology_is_rejected():
    """`assert <real call> is None or True, ""` - a run wrote exactly this.

    The call does the work; the assert around it reports success whatever
    happened, and the empty message leaves nothing to read when it does. It
    was written to get past a gate, which is the shape worth catching: code
    that satisfies a rule without meeting it.
    """
    from validators.method_resolution_validator import validate_step_parameter_types

    errors = validate_step_parameter_types([_page_with_readers(), _step('''
        @then(parsers.parse("the collection holds {n:d}"))
        def assert_holds(widget_page, n):
            assert widget_page.get_result_count() == n or True
    ''')], _PROJECT)

    assert errors, "an `or True` makes the whole expression true regardless"
    assert any("cannot fail" in e for e in errors), errors


def test_asserting_a_call_is_None_is_rejected():
    """A method returning None passes `is None` every time - that asserts the
    signature, not the behaviour."""
    from validators.method_resolution_validator import validate_step_parameter_types

    assert validate_step_parameter_types([_page_with_readers(), _step('''
        @then(parsers.parse("the collection holds {n:d}"))
        def assert_holds(widget_page, n):
            assert widget_page.assert_row_count(n) is None
    ''')], _PROJECT)


def test_a_real_assertion_with_an_or_is_still_allowed():
    """Break the thing the guard guards. `or` is not the problem - a constant
    operand is. Rejecting every disjunction would block legitimate checks."""
    from validators.method_resolution_validator import validate_step_parameter_types

    assert validate_step_parameter_types([_page_with_readers(), _step('''
        @then(parsers.parse("the collection holds {n:d}"))
        def assert_holds(widget_page, n):
            assert widget_page.has_item("a") or widget_page.get_result_count() == n
    ''')], _PROJECT) == []


# =========================================================================
# A METHOD THAT FILLS MUST FIRST REACH ITS OWN PAGE
#
# Filling a field that is not on screen does not fail fast. Playwright waits
# the FULL timeout and then reports the LOCATOR as having timed out - which
# reads like a broken selector when the selector is fine and the page is
# wrong. Thirty seconds spent, and the reader sent to the one place the fault
# is not.
#
# It has cost two stories. The first was a sign-in method, fixed by adding a
# private guard to that one class - which taught the next generated page
# object nothing, so a search method did it again a week later. A fix applied
# to one page object is not a fix; it is a coincidence that page happens to
# be correct.
#
# The primitive now lives on BasePage and the requirement lives at the gate.
# =========================================================================

def _page_object_with(body: str):
    import textwrap
    from types import SimpleNamespace
    return SimpleNamespace(
        file_path="pages/widget_page.py",
        content=("from pages.base_page import BasePage\n\n\n"
                 "class WidgetPage(BasePage):\n"
                 '    INVENTORY_PAGE = "widget"\n\n')
                + textwrap.indent(textwrap.dedent(body).strip("\n"), "    ") + "\n")


def test_filling_without_reaching_the_page_is_rejected():
    """The shape that failed two E2E tests."""
    from validators.method_resolution_validator import (
        validate_fills_confirm_their_page)

    errors = validate_fills_confirm_their_page([_page_object_with('''
        def search_for(self, term: str) -> None:
            self.fill(self.sel("query_field"), term)
            self.click(self.sel("submit_control"))
    ''')], _PROJECT)

    assert errors, "a fill as the opening move asserts a page it never checked"
    assert "require_own_page" in errors[0], "name the fix"
    assert "FULL timeout" in errors[0], (
        "say why it matters - a 30s timeout blaming the locator is what makes "
        "this expensive to diagnose"
    )


def test_reaching_the_page_first_is_accepted():
    """Break the thing the guard guards - the correct form must pass."""
    from validators.method_resolution_validator import (
        validate_fills_confirm_their_page)

    assert validate_fills_confirm_their_page([_page_object_with('''
        def search_for(self, term: str) -> None:
            self.require_own_page()
            self.fill(self.sel("query_field"), term)
    ''')], _PROJECT) == []


def test_a_method_that_clicks_first_is_left_alone():
    """A method that clicks its way somewhere has already established where it
    is. Requiring a precondition on every click would make the rule wrong more
    often than right."""
    from validators.method_resolution_validator import (
        validate_fills_confirm_their_page)

    assert validate_fills_confirm_their_page([_page_object_with('''
        def edit_first_result(self, text: str) -> None:
            self.click(self.sel("first_row"))
            self.fill(self.sel("notes_field"), text)
    ''')], _PROJECT) == []


def test_a_method_that_navigates_itself_is_left_alone():
    from validators.method_resolution_validator import (
        validate_fills_confirm_their_page)

    assert validate_fills_confirm_their_page([_page_object_with('''
        def open_and_search(self, base_url: str, term: str) -> None:
            self.navigate(f"{base_url}/widgets")
            self.fill(self.sel("query_field"), term)
    ''')], _PROJECT) == []


def test_the_check_is_wired_into_the_gate():
    """A validator nothing calls is this project's recurring shape."""
    body = " ".join((_PROJECT / "agents" / "agent2_coder.py").read_text(
        encoding="utf-8").split())

    assert "validate_fills_confirm_their_page(generated_files, PROJECT_ROOT)" in body, (
        "the check is defined but never called - the next page object that "
        "fills would repeat the failure"
    )


def test_the_prompt_teaches_it_before_the_gate_enforces_it():
    """A rule the model can only learn by failing costs an LLM call a run."""
    prompt = (_PROJECT / "prompts" / "agent2_coder_generate.md").read_text(
        encoding="utf-8")

    assert "require_own_page()" in prompt, (
        "the gate requires a helper the prompt never names"
    )