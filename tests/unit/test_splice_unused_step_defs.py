"""A change story's splice must never leave a step definition unused.

Found in validation story A3: the change story revised two scenarios and
retired a third in another story's feature file. Together they took the last
use of a step ("I set the quantity to {quantity:d}"). Agent 2 failed:

    Unused step-definition error ... is defined but no scenario uses it

Three causes, all generic:
  1. the orphan cleanup only REPORTED orphan step definitions (its ai-update
     caller regenerates the file whole) - in the splice path they stayed live;
  2. it only looked at RETIRED scenarios - a revision takes a step's last use
     just as surely;
  3. decorator extraction read commented-out code, so even a commented-out
     orphan still counted as defined (pytest-bdd never registers it).

Run 1 of the same story passed only by luck: the splice added no step
function, so the step-def file was not in the batch and nothing checked it.

Synthetic feature and step files; no application names.
"""
from validators.gherkin_analyzer import (_extract_decorator_phrases,
                                         validate_no_unused_step_definitions)
from validators.orphan_cleanup import comment_out_step_defs_unused_by


class GF:
    def __init__(self, file_path, content):
        self.file_path, self.content = file_path, content


FEATURE_BEFORE = """Feature: Widgets

  Scenario: add several widgets
    When I set the amount to 3
    And I add the widget
    Then the basket shows 3 widget
"""

FEATURE_AFTER = """Feature: Widgets

  Scenario: add one widget
    When I add the widget
    Then the basket shows 1 widget
"""

STEPS = '''from pytest_bdd import parsers, then, when


@when(parsers.parse("I set the amount to {amount:d}"))
def set_amount(widget_page, amount):
    widget_page.set_amount(amount)


@when("I add the widget")
def add_widget(widget_page):
    widget_page.add()


@then(parsers.parse("the basket shows {n:d} widget"))
def basket_shows(basket_page, n):
    assert basket_page.count() == n
'''


def _clean(steps=STEPS, feature=FEATURE_AFTER, before=FEATURE_BEFORE):
    return comment_out_step_defs_unused_by(
        before, feature, steps, "tests/step_defs/test_widgets.py", "features/widgets.feature",
        "AB-9", ["AB-2", "AB-3"])


def test_a_step_the_change_left_unused_is_commented_out_and_reported():
    content, orphans = _clean()
    assert [o.function_name for o in orphans] == ["set_amount"]
    assert '# @when(parsers.parse("I set the amount to {amount:d}"))' in content
    assert "    # widget_page.set_amount(amount)" in content
    assert "AI-ORPHAN" in content and "AB-9" in content


def test_after_cleanup_the_unused_step_check_passes():
    """The exact gate that failed the run: it must now be green."""
    before = validate_no_unused_step_definitions(
        [GF("features/widgets.feature", FEATURE_AFTER),
         GF("tests/step_defs/test_widgets.py", STEPS)])
    assert len(before) == 1 and "I set the amount" in before[0]
    content, _ = _clean()
    assert validate_no_unused_step_definitions(
        [GF("features/widgets.feature", FEATURE_AFTER),
         GF("tests/step_defs/test_widgets.py", content)]) == []


def test_used_steps_are_untouched_and_the_file_still_compiles():
    content, _ = _clean()
    assert '@when("I add the widget")\ndef add_widget' in content
    assert '@then(parsers.parse("the basket shows {n:d} widget"))' in content
    compile(content, "x.py", "exec")


def test_nothing_unused_changes_nothing():
    feature = FEATURE_AFTER + "    When I set the amount to 3\n"
    content, orphans = _clean(feature=feature)
    assert content == STEPS and orphans == []


def test_a_function_keeping_one_used_decorator_loses_only_the_dead_one():
    steps = '''from pytest_bdd import then, when


@when("I add the widget")
@when("I put the widget in")
def add_widget(widget_page):
    widget_page.add()


@then(parsers.parse("the basket shows {n:d} widget"))
def basket_shows(basket_page, n):
    assert basket_page.count() == n
'''
    before = FEATURE_BEFORE + "    And I put the widget in\n"
    content, orphans = _clean(steps=steps, before=before)
    assert [o.function_name for o in orphans] == ["add_widget"]
    assert '\n@when("I add the widget")\n' in content            # live step kept
    assert '# @when("I put the widget in")' in content
    assert "\ndef add_widget(widget_page):" in content           # function live
    compile(content, "x.py", "exec")


def test_a_keyword_mismatch_still_counts_as_used():
    """Keyword-agnostic, exactly like the unused-step check and pytest-bdd's
    And/But dispatch: a Then-step bound by @when is used, not orphaned."""
    feature = FEATURE_AFTER + "    And I set the amount to 2\n"
    content, orphans = _clean(feature=feature)
    assert orphans == [] and content == STEPS


def test_a_step_already_unused_before_the_change_is_not_this_changes_to_touch():
    before = FEATURE_AFTER          # the amount step was unused already
    content, orphans = _clean(before=before)
    assert orphans == [] and content == STEPS


def test_unparseable_step_defs_are_left_alone():
    content, orphans = _clean(steps="def broken(:\n")
    assert content == "def broken(:\n" and orphans == []


def test_commented_out_decorators_are_not_definitions():
    """pytest-bdd never registers a commented-out decorator, so no validator
    may count one - neither as unused nor as covering a step."""
    text = ('# @when("I do the old thing")\n#     pass\n'
            '    # @then(parsers.parse("x {n:d}"))\n'
            '@when("I do the new thing")\ndef new():\n    pass\n')
    assert _extract_decorator_phrases(text) == [("when", "I do the new thing", "string")]
