"""An absence step is never asserted through a predicate that waits for
presence: the gate points at the page object's answering method (or at the
page object when there is none), and the rule is one the repair loop can fix.
"""

from pathlib import Path
import pytest
from core.schemas import GeneratedFile


PAGE = '''from pages.base_page import BasePage


class WidgetPage(BasePage):
    def has_badge(self) -> bool:
        return self.is_showing(self.sel("badge"))
{extra}'''
ALT = '''
    def badge_count(self) -> int:
        return self.get_count(self.sel("badge"))
'''


def _steps(body):
    return ("from pytest_bdd import then\n\n\n@then('the badge is gone')\n"
            f"def _(widget_page):\n    {body}\n")


def _absence(step_body, extra=ALT):
    from validators.method_resolution_validator import (
        validate_absence_not_asserted_with_waiting_probe as v,
    )
    files = [GeneratedFile(file_path="pages/widget_page.py", content=PAGE.format(extra=extra),
                           is_new_file=True, purpose="p"),
             GeneratedFile(file_path="tests/step_defs/test_widget.py",
                           content=_steps(step_body), is_new_file=True, purpose="s")]
    return v(files, Path("/nonexistent"))


def test_absence_through_a_waiting_predicate_points_at_the_answer():
    errors = _absence("assert not widget_page.has_badge()")
    assert len(errors) == 1
    assert errors[0].startswith("Absence assertion error in 'tests/step_defs/test_widget.py'")
    assert "WidgetPage.badge_count()" in errors[0]


def test_absence_with_no_answering_method_points_at_the_page_object():
    errors = _absence("assert widget_page.has_badge() is False", extra="")
    assert len(errors) == 1
    assert errors[0].startswith("Absence assertion error in 'pages/widget_page.py'")
    assert 'self.is_gone(self.sel("badge"))' in errors[0]   # the absence wait (A3)


@pytest.mark.parametrize("body", ["assert widget_page.has_badge()",
                                  "assert widget_page.badge_count() == 0"])
def test_presence_and_a_non_waiting_absence_pass(body):
    assert _absence(body) == []


def test_the_absence_rule_is_repairable():
    import inspect

    import agents.agent2_coder as a2
    assert "validate_absence_not_asserted_with_waiting_probe" in \
        inspect.getsource(a2._collect_repairable_errors)
    assert a2._classify_error("Absence assertion error in 'x': ...") == "absence_waits"
