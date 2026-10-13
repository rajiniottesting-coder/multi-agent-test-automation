"""An absence predicate has an answer every gate accepts.

Found in validation story A3 (Agent 2, third run): the model wrote

    def is_<field>_absent(self) -> bool:
        return not self.is_visible(self.sel("<key>"))

The predicate rule rejected it and told the model to use is_showing() - a
PRESENCE wait, which answers "absent" only by exhausting its timeout and which
the absence rule rejects. No rewrite satisfied both gates: the repair loop
stalled ("changed nothing") and the run failed.

Now BasePage.is_gone() is the absence wait, the predicate rule names it for a
negated glance, the absence rule accepts and suggests it, and the prompt shows
it. Synthetic page objects; no application names.
"""
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import pages.base_page as bp
from validators.method_resolution_validator import (
    validate_absence_not_asserted_with_waiting_probe, validate_predicates_wait)

ROOT = Path(__file__).resolve().parents[2]

PAGE = '''from pages.base_page import BasePage


class WidgetPage(BasePage):
    INVENTORY_PAGE = "widget"

    def {name}(self) -> bool:
        return {body}
'''


def _page(name, body):
    return SimpleNamespace(file_path="pages/widget_page.py",
                           content=PAGE.format(name=name, body=body))


@pytest.mark.parametrize("probe", ["is_visible", "exists"])
def test_a_negated_glance_is_pointed_at_is_gone_not_is_showing(probe):
    errs = validate_predicates_wait([_page("is_knob_absent", f'not self.{probe}(self.sel("knob"))')])
    assert len(errs) == 1
    assert "self.is_gone(" in errs[0]
    assert "Do NOT use is_showing()" in errs[0]


def test_the_suggested_fix_passes_the_predicate_rule():
    assert validate_predicates_wait([_page("is_knob_absent", 'self.is_gone(self.sel("knob"))')]) == []


def test_the_suggested_fix_passes_the_absence_rule_too():
    """The step that asserts it is True must not trip the absence gate."""
    page = _page("is_knob_absent", 'self.is_gone(self.sel("knob"))')
    step = SimpleNamespace(file_path="tests/step_defs/test_widget.py", content='''
from pytest_bdd import then

@then("the knob is not shown")
def knob_absent(widget_page):
    assert widget_page.is_knob_absent()
''')
    assert validate_absence_not_asserted_with_waiting_probe([page, step], ROOT) == []


def test_a_presence_glance_still_gets_the_presence_remedy():
    errs = validate_predicates_wait([_page("is_knob_shown", 'self.is_visible(self.sel("knob"))')])
    assert len(errs) == 1 and "self.is_showing(" in errs[0] and "is_gone" not in errs[0]


def test_the_absence_rule_suggests_is_gone():
    page = SimpleNamespace(file_path="pages/widget_page.py", content=PAGE.format(
        name="has_knob", body='self.is_showing(self.sel("knob"))'))
    step = SimpleNamespace(file_path="tests/step_defs/test_widget.py", content='''
from pytest_bdd import then

@then("the knob is not shown")
def knob_absent(widget_page):
    assert not widget_page.has_knob()
''')
    errs = validate_absence_not_asserted_with_waiting_probe([page, step], ROOT)
    assert len(errs) == 1 and "self.is_gone(" in errs[0]


def test_is_gone_exists_and_the_prompt_shows_it():
    assert "timeout_ms" in inspect.signature(bp.BasePage.is_gone).parameters
    text = (ROOT / "prompts" / "agent2_coder_generate.md").read_text(encoding="utf-8")
    assert 'return self.is_gone(self.sel("<key>"))' in text
