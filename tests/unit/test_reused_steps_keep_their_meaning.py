"""A step phrase means the same thing in every feature.

pytest-bdd binds steps per module, so a phrase defined for one feature is
written again for the next. Validation story SCRUM-187: "the search results
should include X" was committed as a containment check; Agent 2's new copy also
asserted that the search-results view was shown, and its own empty-search
scenario - which keeps the unsearched view - failed in the browser on that
extra, unstated check. validate_reused_steps_keep_their_meaning() stops that at
the gate. Generic names only.
"""
import textwrap

from core.schemas import GeneratedFile
from validators.method_resolution_validator import (
    _phrase_template,
    validate_reused_steps_keep_their_meaning as check,
)

COMMITTED = textwrap.dedent('''
    from pytest_bdd import parsers, then

    @then(parsers.re(r'the list should include "(?P<name>[^"]*)"'))
    def includes(widget_page, name):
        assert widget_page.has_item(name), f"{name} missing"

    @then("the banner is shown")
    def banner(widget_page):
        assert widget_page.is_banner_shown()
''')


def _root(tmp_path):
    d = tmp_path / "tests" / "step_defs"
    d.mkdir(parents=True)
    (d / "test_widgets.py").write_text(COMMITTED)
    return tmp_path


def _gen(body):
    return [GeneratedFile(file_path="tests/step_defs/test_new_flow.py", is_new_file=True,
                          purpose="t", content=textwrap.dedent(body))]


def test_placeholders_written_by_any_parser_are_one_phrase():
    assert _phrase_template(r'the list should include "(?P<name>[^"]*)"') == \
        _phrase_template('the list should include "{name}"') == \
        _phrase_template('the list should include "{name:w}"')


def test_an_extra_unstated_check_is_rejected_and_names_both_files(tmp_path):
    [err] = check(_gen('''
        from pytest_bdd import parsers, then

        @then(parsers.parse('the list should include "{name}"'))
        def includes(widget_page, name):
            assert widget_page.is_results_view_shown(), "view"
            assert widget_page.has_item(name), "missing"
    '''), _root(tmp_path))
    assert "tests/step_defs/test_widgets.py" in err and "has_item()" in err
    assert "is_results_view_shown()" in err and "its own Then step" in err


def test_the_same_check_or_a_subset_passes(tmp_path):
    root = _root(tmp_path)
    assert check(_gen('''
        from pytest_bdd import parsers, then

        @then(parsers.parse('the list should include "{name}"'))
        def includes(widget_page, name):
            assert widget_page.has_item(name), f"{name} missing"
    '''), root) == []


def test_actions_are_not_claims_and_new_phrases_are_free(tmp_path):
    root = _root(tmp_path)
    assert check(_gen('''
        from pytest_bdd import parsers, then

        @then(parsers.parse('the list should include "{name}"'))
        def includes(widget_page, name):
            widget_page.wait_for_item(name)
            assert widget_page.has_item(name)

        @then("a brand new sentence holds")
        def fresh(widget_page):
            assert widget_page.is_results_view_shown() and widget_page.has_item("x")
    '''), root) == []


def test_given_and_when_are_not_checked(tmp_path):
    assert check(_gen('''
        from pytest_bdd import given

        @given("the banner is shown")
        def banner(widget_page):
            assert widget_page.open_and_check()
    '''), _root(tmp_path)) == []


def test_a_file_being_regenerated_is_not_compared_with_its_old_self(tmp_path):
    root = _root(tmp_path)
    files = [GeneratedFile(file_path="tests/step_defs/test_widgets.py", is_new_file=False,
                           purpose="t", content=COMMITTED.replace(
                               "assert widget_page.has_item(name)",
                               "assert widget_page.is_results_view_shown()\n"
                               "        assert widget_page.has_item(name)"))]
    assert check(files, root) == []


def test_committed_step_definitions_agree_with_each_other():
    """No committed module re-defines a phrase with an extra check today, so
    the rule rejects nothing that already works."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for path in sorted((root / "tests" / "step_defs").glob("test_*.py")):
        files = [GeneratedFile(file_path=path.relative_to(root).as_posix(), is_new_file=False,
                               purpose="t", content=path.read_text(encoding="utf-8"))]
        assert check(files, root) == [], path.name


def test_the_rule_runs_in_the_repair_loop_and_the_gate():
    import inspect
    import agents.agent2_coder as a2
    assert "validate_reused_steps_keep_their_meaning" in inspect.getsource(
        a2._collect_repairable_errors)


def test_the_prompt_teaches_it():
    from config.paths import PROMPTS_DIR
    text = (PROMPTS_DIR / "agent2_coder_generate.md").read_text(encoding="utf-8")
    assert "asserts exactly what its sentence says, and nothing more" in text
