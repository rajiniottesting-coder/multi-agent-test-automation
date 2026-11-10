"""A step carries no data table or doc string the pinned runner cannot read
(validators/step_arguments.py). 10 Nov 2026: a generated step followed by a
table of values passed the gate and failed every run with
StepDefinitionNotFoundError."""
from types import SimpleNamespace as NS

import pytest

from validators import step_arguments
from validators.step_arguments import validate_steps_carry_no_table_or_doc_string as check

FEATURE = '''Feature: x
  Background:
    Given I am on the list page

  Scenario: The list shows its entries
    Then the list shows the following entries
      | entry |
      | A (6) |
    And the list shows a heading

  Scenario Outline: The list finds <name>
    When I search for "<name>"
    Then the list shows "<name>"

    Examples:
      | name |
      | A    |

  Scenario: A note
    Then the page says
      """
      hello
      """
'''


def _f(content):
    return [NS(file_path="features/list.feature", content=content)]


def test_a_table_or_doc_string_under_a_step_is_refused_examples_are_not(monkeypatch):
    monkeypatch.setattr(step_arguments, "runner_reads_step_arguments", lambda: False)
    errors = check(_f(FEATURE))
    assert len(errors) == 2
    assert errors[0].startswith("Step argument error in 'features/list.feature': the step "
                                "`Then the list shows the following entries` is followed by "
                                "a data table.")
    assert "`Then the page says` is followed by a doc string" in errors[1]
    assert not any("search for" in e or "<name>" in e for e in errors)


def test_a_runner_that_reads_step_arguments_is_left_alone(monkeypatch):
    monkeypatch.setattr(step_arguments, "runner_reads_step_arguments", lambda: True)
    assert check(_f(FEATURE)) == []


def test_the_installed_runner_is_what_decides():
    from importlib.metadata import version
    major = int(version("pytest-bdd").split(".")[0])
    assert step_arguments.runner_reads_step_arguments() is (major >= 8)


@pytest.mark.parametrize("content", ["Feature: y\n  Scenario: s\n    Then it works\n", ""])
def test_plain_features_pass(content, monkeypatch):
    monkeypatch.setattr(step_arguments, "runner_reads_step_arguments", lambda: False)
    assert check(_f(content)) == []
