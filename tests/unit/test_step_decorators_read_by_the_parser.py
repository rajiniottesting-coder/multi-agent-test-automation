"""Step decorators are read as Python reads them, not by a pattern.

3 Nov 2026, SCRUM-284: the generated step definition wrapped a long phrase
over several string literals - Python's usual way to break a long line, joined
into one string before pytest-bdd sees it:

    @when(parsers.re(
        'I fill in the form with name "(?P<name>[^"]*)", '
        'email "(?P<email>[^"]*)", ...'
    ))

The validators read a phrase with a pattern that stopped at its first closing
quote, so they saw `I fill in ... name "(?P<name>[^"]*)", '` plus indentation:
"no matching decorator", "unused step definition" and "drifted wording" for a
step pytest-bdd resolves. Four repair attempts "fixed" a non-problem; the story
was blocked with a message blaming the model and the test case ($1.50).
A decorator with keyword arguments (target_fixture=...) was not seen at all.

Now the file is parsed (ast): literals joined, escapes resolved, comments
dropped. A file that does not parse falls back to the patterns, as before.
Generic phrases only.
"""
import pytest

from core.schemas import GeneratedFile
from validators.gherkin_analyzer import (
    _extract_decorator_phrases,
    validate_step_coverage,
)

WRAPPED = '''from pytest_bdd import given, when, then, parsers


@given(parsers.parse('I open the {page} page'), target_fixture="opened")
def open_page(page):
    return page


@when(parsers.re(
    'I fill in the form with name "(?P<name>[^"]*)", '
    'email "(?P<email>[^"]*)" and message "(?P<message>[^"]*)"'
))
def fill(name, email, message):
    pass


@then(
    "the confirmation "
    "\\"Thank you\\" is shown"
)
def confirmed():
    pass
'''

FEATURE = '''Feature: A form

  Scenario: Sending the form
    Given I open the contact page
    When I fill in the form with name "Ann", email "ann@example.com" and message "Hi"
    Then the confirmation "Thank you" is shown

  Scenario: Sending the form without an email
    Given I open the contact page
    When I fill in the form with name "Ann", email "" and message "Hi"
    Then the confirmation "Thank you" is shown
'''


def test_wrapped_phrases_are_joined_as_python_joins_them():
    assert _extract_decorator_phrases(WRAPPED) == [
        ("given", "I open the {page} page", "parse"),
        ("when", 'I fill in the form with name "(?P<name>[^"]*)", '
                 'email "(?P<email>[^"]*)" and message "(?P<message>[^"]*)"', "re"),
        ("then", 'the confirmation "Thank you" is shown', "string"),
    ]


def _files(feature, step_defs):
    return [GeneratedFile(file_path="features/form.feature", content=feature),
            GeneratedFile(file_path="tests/step_defs/test_form.py", content=step_defs)]


def test_the_scenario_that_failed_validates_clean():
    assert validate_step_coverage(_files(FEATURE, WRAPPED)) == []


def test_the_patterns_alone_failed_it(monkeypatch):
    """The regression, pinned: without the parser the same files fail."""
    import validators.gherkin_analyzer as ga
    monkeypatch.setattr(ga, "_decorators_from_ast", lambda src: None)
    errors = validate_step_coverage(_files(FEATURE, WRAPPED))
    assert errors, "the patterns cannot read a wrapped phrase"


def test_a_step_really_missing_is_still_reported():
    errors = validate_step_coverage(_files(FEATURE + "    And a step nobody defined\n", WRAPPED))
    assert errors and any("a step nobody defined" in e for e in errors)


@pytest.mark.parametrize("source, expected", [
    # commented out: pytest-bdd never registers it
    ("# @when('gone')\n@when('kept')\ndef f(): pass\n", [("when", "kept", "string")]),
    # the module-qualified form and the keyword form
    ("import pytest_bdd\n@pytest_bdd.then(name='done')\ndef f(): pass\n",
     [("then", "done", "string")]),
    # a parser imported by name
    ("from pytest_bdd.parsers import cfparse\n@given(cfparse('{n:d} items'))\ndef f(n): pass\n",
     [("given", "{n:d} items", "cfparse")]),
    # not a step decorator, or a phrase only known at runtime
    ("@pytest.fixture\ndef a(): pass\n@when(PHRASE)\ndef b(): pass\n", []),
    # a raw string keeps its backslashes, as the regex needs
    (r"""@when(parsers.re(r'a \d+ (?P<x>\w+)'))""" + "\ndef f(x): pass\n",
     [("when", r"a \d+ (?P<x>\w+)", "re")]),
])
def test_what_pytest_bdd_registers(source, expected):
    assert _extract_decorator_phrases(source) == expected


def test_source_order_is_kept():
    src = "@then('c')\ndef c(): pass\n@given('a')\ndef a(): pass\n@when('b')\ndef b(): pass\n"
    assert [p for _k, p, _t in _extract_decorator_phrases(src)] == ["c", "a", "b"]


def test_a_file_that_does_not_parse_falls_back_to_the_patterns():
    src = "@when(parsers.parse('I click {item}'))\ndef f(item:\n    pass\n"
    assert _extract_decorator_phrases(src) == [("when", "I click {item}", "parse")]
