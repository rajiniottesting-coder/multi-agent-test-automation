"""The two composite entry points must return exactly what the parts returned.

WHY THIS EXISTS
    Sixteen separate validators is a lot to hold in one head, and two clusters
    genuinely ask one question in several ways:

      - three rules about what a page-object METHOD DEFINITION may look like
      - three checks that read a feature file against its step definitions

    Clubbing them is worth doing, and refactoring a gate is exactly the kind of
    change that quietly loses a rule — the suite stays green because each part
    is still tested individually, while the composite silently drops one.

    So each composite is checked against the parts it replaces, on the same
    input, requiring the same list in the same order. Not "no errors" — the
    SAME errors.

WHAT WAS DELIBERATELY NOT MERGED
    validate_method_resolution judges a CALL in a step definition against the
    page object it names. It reads like a fourth "method" check and is not:
    different input, different failure, different fix. Folding it in would hide
    that, and the error the model gets back is how it knows which of those to
    reach for.

    validate_page_object_selectors judges the selectors a method uses, not the
    method itself.

    validate_no_duplicate_step_definitions is a no-op by design (ADR-013) and
    stays registered so the belief it disproves cannot quietly return.
"""
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.gherkin_analyzer import (
    detect_drifted_steps,
    validate_no_unused_step_definitions,
    validate_step_coverage,
    validate_step_definitions_complete,
)
from validators.method_resolution_validator import (
    validate_no_duplicate_page_object_methods,
    validate_page_method_names_are_specific,
    validate_page_object_methods,
    validate_predicates_wait,
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
# Cluster 1 — page-object method shape
# ─────────────────────────────────────────────────────────────────────────

_METHOD_CASES = [
    ("clean", '''
        def open_widget(self, base_url: str) -> None:
            self.navigate(base_url)

        def is_loaded(self) -> bool:
            return self.is_showing(self.sel("panel"))
    '''),
    ("bare verb", '''
        def open(self, base_url: str) -> None:
            self.navigate(base_url)
    '''),
    ("duplicate pair", '''
        def filter_by_brand(self, brand: str) -> None:
            self.click(self.sel("brand"))

        def filter_widget_by_brand(self, brand: str) -> None:
            self.click(self.sel("brand"))
    '''),
    ("non-waiting predicate", '''
        def is_empty(self) -> bool:
            return self.is_visible(self.sel("empty_message"))
    '''),
    ("all three at once", '''
        def open(self, base_url: str) -> None:
            self.navigate(base_url)

        def open_widget(self, name: str) -> None:
            self.click(self.sel("links"))

        def is_empty(self) -> bool:
            return self.is_visible(self.sel("empty_message"))
    '''),
]


@pytest.mark.parametrize("label,body", _METHOD_CASES, ids=[c[0] for c in _METHOD_CASES])
def test_the_method_composite_equals_its_parts(label, body):
    files = [_page(body)]

    parts = (validate_no_duplicate_page_object_methods(files)
             + validate_page_method_names_are_specific(files)
             + validate_predicates_wait(files))

    assert validate_page_object_methods(files) == parts, (
        f"the composite and the three parts disagree on the {label!r} case. A "
        f"refactor that drops a rule keeps every individual test green — this "
        f"is the only check that would notice."
    )


def test_the_method_composite_actually_finds_things():
    """A composite that returned [] for everything would pass the equivalence
    test above only if the parts did too. This pins that the corpus is real."""
    found = {label: len(validate_page_object_methods([_page(body)]))
             for label, body in _METHOD_CASES}
    assert found["clean"] == 0
    assert found["bare verb"] >= 1
    assert found["duplicate pair"] >= 1
    assert found["non-waiting predicate"] >= 1
    assert found["all three at once"] >= 3, found


# ─────────────────────────────────────────────────────────────────────────
# Cluster 2 — feature file against its step definitions
#
# The pairing rule moved out of agents/agent2_coder.py. This reimplements the
# old composition here, verbatim, and requires the moved version to match it.
# ─────────────────────────────────────────────────────────────────────────

def _the_old_way(files):
    """The composition exactly as agents/agent2_coder.py used to do it."""
    import re

    errors = []
    coverage_errors = validate_step_definitions_complete(files)
    unused_errors = validate_no_unused_step_definitions(files)
    drifted, drift_phrases = detect_drifted_steps(files)
    if drifted:
        def _explained(err):
            quoted = [q[1:-1].strip() for q in re.findall(r"`[^`]+`|'[^']+'", err)]

            def _bare(p):
                parts = p.split(None, 1)
                return parts[1] if len(parts) == 2 and parts[0].lower() in (
                    "given", "when", "then", "and", "but") else p

            return any(q and (_bare(q) in drift_phrases or q in drift_phrases)
                       for q in quoted)

        coverage_errors = [e for e in coverage_errors if not _explained(e)]
        unused_errors = [e for e in unused_errors if not _explained(e)]
        errors.extend(drifted)
    errors.extend(coverage_errors)
    errors.extend(unused_errors)
    return errors


def _batch(feature: str, steps: str):
    return [
        SimpleNamespace(file_path="features/widget.feature",
                        content=textwrap.dedent(feature)),
        SimpleNamespace(file_path="tests/step_defs/test_widget.py",
                        content=textwrap.dedent(steps)),
    ]


_COVERAGE_CASES = [
 ("everything matches", '''
    Feature: Widgets

      Scenario: Open a widget
        Given I am on the widget page
  ''', '''
    from pytest_bdd import scenarios, given

    scenarios("widget.feature")


    @given("I am on the widget page")
    def open_page(widget_page):
        widget_page.open_widget("")
  '''),

 ("a step with no definition", '''
    Feature: Widgets

      Scenario: Open a widget
        Given I am on the widget page
        When I click the widget
  ''', '''
    from pytest_bdd import scenarios, given

    scenarios("widget.feature")


    @given("I am on the widget page")
    def open_page(widget_page):
        widget_page.open_widget("")
  '''),

 ("a definition nothing uses", '''
    Feature: Widgets

      Scenario: Open a widget
        Given I am on the widget page
  ''', '''
    from pytest_bdd import scenarios, given, when

    scenarios("widget.feature")


    @given("I am on the widget page")
    def open_page(widget_page):
        widget_page.open_widget("")


    @when("I do something nothing asks for")
    def unused(widget_page):
        pass
  '''),

 ("drift — the pair that used to oscillate", '''
    Feature: Widgets

      Scenario: Open a widget
        Given I am on the widget page
        Then the widget should be open
  ''', '''
    from pytest_bdd import scenarios, given, then

    scenarios("widget.feature")


    @given("I am on the widget page")
    def open_page(widget_page):
        widget_page.open_widget("")


    @then("the widget should be open now")
    def assert_open(widget_page):
        assert widget_page.is_loaded()
  '''),
]


@pytest.mark.parametrize("label,feature,steps", _COVERAGE_CASES,
                         ids=[c[0] for c in _COVERAGE_CASES])
def test_the_coverage_composite_equals_the_old_inline_composition(label, feature, steps):
    files = _batch(feature, steps)

    assert validate_step_coverage(files) == _the_old_way(files), (
        f"validate_step_coverage() and the composition it replaced disagree on "
        f"the {label!r} case. The pairing rule was moved verbatim; any "
        f"difference here means it was not."
    )


def test_a_drifted_pair_still_speaks_once():
    """The reason the pairing exists. Both halves must be suppressed, or the
    model oscillates: deleting the decorator fixes 'unused' and creates
    'missing coverage', and back again."""
    label, feature, steps = _COVERAGE_CASES[3]
    errors = validate_step_coverage(_batch(feature, steps))

    assert errors, "the drifted pair produced nothing at all"
    assert len(errors) == 1, (
        f"a drifted pair must produce ONE instruction, got {len(errors)}:\n  "
        + "\n  ".join(errors)
    )