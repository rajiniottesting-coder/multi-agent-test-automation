"""Every error the repair loop collects reaches a file the model is asked to fix.

Validation story SCRUM-187 (20 Oct 2026): a new rule worded its errors
`<path>: step ...`. The grouper reads `<rule> in '<path>':`, so it dropped the
error, no repair was attempted, and the story failed at the final gate on
feedback the model was never shown. The format contract in test_repair_loop.py
only covers the validators its sample batch happens to trigger; this one
replaces every validator in the repairable set with one that words its error
in an arbitrary way, so a rule added later is covered without anyone
remembering to sample it. Generic names only.
"""
import inspect
import re
import textwrap

import pytest

import agents.agent2_coder as a2
from core.schemas import GeneratedFile
from validators.method_resolution_validator import validate_reused_steps_keep_their_meaning

GEN = "tests/step_defs/test_new_flow.py"


def _validators_in_the_repair_set() -> list:
    body = inspect.getsource(a2._collect_repairable_errors)
    names = re.findall(r"errors\.extend\(\s*(validate_\w+)\(", body)
    assert len(names) >= 20, names          # the set is read, not assumed empty
    return sorted(set(names))


@pytest.mark.parametrize("wording", [
    "{p}: the step says one thing and checks another",
    "{p} line 7: something is wrong",
    "Something is wrong with {p}, see line 7",
])
def test_any_wording_from_any_validator_is_routed(monkeypatch, wording):
    files = [GeneratedFile(file_path=GEN, is_new_file=True, purpose="t", content="")]
    names = _validators_in_the_repair_set()
    for name in names:
        monkeypatch.setattr(a2, name, lambda *a, _n=name, **k: [
            f"[{_n}] " + wording.format(p=GEN)])

    errors = a2._collect_repairable_errors(files)
    grouped = a2._group_validator_errors_by_file(errors)

    assert len(errors) == len(names)
    assert sorted(grouped) == [GEN]
    assert len(grouped[GEN]) == len(names), "an error was dropped before repair"


def test_the_generated_file_wins_over_a_committed_file_it_mentions():
    files = [GeneratedFile(file_path=GEN, is_new_file=True, purpose="t", content="")]
    err = f"step 'x' is already defined in tests/step_defs/test_old.py, unlike {GEN}"
    [routed] = a2._route_to_generated_file([err], files)
    assert a2._group_validator_errors_by_file([routed]) == {GEN: [routed]}


def test_a_routable_error_is_left_unchanged_and_one_naming_no_file_too():
    files = [GeneratedFile(file_path=GEN, is_new_file=True, purpose="t", content="")]
    ok = f"Step coverage error in '{GEN}': missing @then"
    loose = "Something odd happened"
    assert a2._route_to_generated_file([ok, loose], files) == [ok, loose]


def test_the_reused_step_rule_itself_reaches_the_repair_loop(tmp_path):
    """The exact SCRUM-187 failure: a re-defined Then that checks more than
    the committed one. Its error must land on the generated step file."""
    d = tmp_path / "tests" / "step_defs"
    d.mkdir(parents=True)
    (d / "test_session.py").write_text(textwrap.dedent('''
        from pytest_bdd import then

        @then("I should not be signed in")
        def not_signed_in(account_page):
            assert not account_page.is_signed_in()
    '''))
    files = [GeneratedFile(file_path=GEN, is_new_file=True, purpose="t", content=textwrap.dedent('''
        from pytest_bdd import then

        @then("I should not be signed in")
        def not_signed_in(account_page):
            assert account_page.wait_until_signed_out()
            assert not account_page.is_signed_in()
    '''))]
    [err] = validate_reused_steps_keep_their_meaning(files, tmp_path)
    assert err.startswith(f"Reused step meaning error in '{GEN}':")
    assert a2._group_validator_errors_by_file([err]) == {GEN: [err]}


# --- prevention: the model sees the committed definition before writing ---

def _feature(text):
    return GeneratedFile(file_path="features/new_flow.feature", is_new_file=True,
                         purpose="t", content=textwrap.dedent(text))


def _committed(tmp_path):
    d = tmp_path / "tests" / "step_defs"
    d.mkdir(parents=True)
    (d / "test_session.py").write_text(textwrap.dedent('''
        from pytest_bdd import parsers, then

        @then("I should not be signed in")
        def not_signed_in(account_page):
            assert not account_page.is_signed_in()

        @then(parsers.re(r'the list should include "(?P<name>[^"]*)"'))
        def includes(widget_page, name):
            assert widget_page.has_item(name)
    '''))
    return tmp_path


def test_reused_then_steps_are_shown_with_their_committed_body(tmp_path):
    from types import SimpleNamespace
    plan = SimpleNamespace(file_type="step_definitions", file_path=GEN)
    feature = _feature('''
        Feature: f
          Scenario: s
            When I sign out
            Then I should not be signed in
            And the list should include "Item A"
            And something new is shown
    ''')
    block = a2._build_reused_then_steps_block(plan, [feature], _committed(tmp_path))
    assert '- "I should not be signed in" - tests/step_defs/test_session.py:' in block
    assert "assert not account_page.is_signed_in()" in block
    assert 'the list should include "Item A"' in block and "has_item(name)" in block
    assert "something new" not in block and "assert EXACTLY" in block


def test_no_block_for_new_phrases_other_file_types_or_given_when(tmp_path):
    from types import SimpleNamespace
    root = _committed(tmp_path)
    feature = _feature('''
        Feature: f
          Scenario: s
            Given I should not be signed in
            Then a brand new outcome
    ''')
    steps = SimpleNamespace(file_type="step_definitions", file_path=GEN)
    page = SimpleNamespace(file_type="page_object", file_path="pages/x_page.py")
    assert a2._build_reused_then_steps_block(steps, [feature], root) == ""
    assert a2._build_reused_then_steps_block(page, [feature], root) == ""


def test_a_file_being_regenerated_is_not_its_own_reference(tmp_path):
    from types import SimpleNamespace
    root = _committed(tmp_path)
    plan = SimpleNamespace(file_type="step_definitions",
                           file_path="tests/step_defs/test_session.py")
    feature = _feature('''
        Feature: f
          Scenario: s
            Then I should not be signed in
    ''')
    assert a2._build_reused_then_steps_block(plan, [feature], root) == ""
