"""
Unit tests for validate_no_duplicate_step_definitions.

UPDATED (ADR-013): cross-file step duplication is SAFE in pytest-bdd. Step
definitions are pytest FIXTURES and are MODULE-SCOPED, so two step-def modules
declaring the same step text each resolve their own copy — they never collide.
Verified empirically.

The original SCRUM-54 belief ("pytest-bdd registers step definitions globally
across the step_defs package") was false. The validator is now a no-op, which
is what lets every generated step-def file be SELF-CONTAINED.

These tests pin the CORRECT behaviour: duplication is never reported.
"""
from pathlib import Path

import pytest

from validators.gherkin_analyzer import validate_no_duplicate_step_definitions


def _gf(path, content):
    """Minimal GeneratedFile-like object (validator uses .file_path / .content)."""
    class _F:
        def __init__(self, p, c):
            self.file_path = p
            self.content = c
    return _F(path, content)


# ─────────────────────────────────────────────────────────────
# CROSS-FILE DUPLICATION — safe in pytest-bdd, must NOT be flagged
# ─────────────────────────────────────────────────────────────

def test_identical_given_across_two_generated_files():
    files = [
        _gf("tests/step_defs/test_a.py",
            '@given("I am on the login page")\ndef _(): pass'),
        _gf("tests/step_defs/test_b.py",
            '@given("I am on the login page")\ndef _(): pass'),
    ]
    errors = validate_no_duplicate_step_definitions(files)
    assert errors == []  # module-scoped fixtures: never a collision


def test_identical_parse_decorator_across_files():
    files = [
        _gf("tests/step_defs/test_a.py",
            '@when(parsers.parse("I log in as \\"{user}\\""))\ndef _(): pass'),
        _gf("tests/step_defs/test_b.py",
            '@when(parsers.parse("I log in as \\"{user}\\""))\ndef _(): pass'),
    ]
    errors = validate_no_duplicate_step_definitions(files)
    assert errors == []  # module-scoped fixtures: never a collision


def test_collision_against_reference_on_disk(tmp_path):
    """A generated file colliding with the on-disk reference must be caught."""
    step_defs = tmp_path / "tests" / "step_defs"
    step_defs.mkdir(parents=True)
    (step_defs / "test_login.py").write_text(
        '@given("I am on the login page")\ndef _(): pass', encoding="utf-8")

    files = [
        _gf("tests/step_defs/test_login_edge.py",
            '@given("I am on the login page")\ndef _(): pass'),
    ]
    errors = validate_no_duplicate_step_definitions(files, project_root=tmp_path)
    assert errors == []  # module-scoped fixtures: never a collision


# ─────────────────────────────────────────────────────────────
# TRUE NEGATIVES — must NOT be flagged (false-positive guards)
# ─────────────────────────────────────────────────────────────

def test_different_phrases_no_collision():
    files = [
        _gf("tests/step_defs/test_a.py", '@given("I am on the login page")\ndef _(): pass'),
        _gf("tests/step_defs/test_b.py", '@given("I am on the cart page")\ndef _(): pass'),
    ]
    assert validate_no_duplicate_step_definitions(files) == []


def test_same_phrase_different_keyword_no_collision():
    """given vs when with the same text are different registrations."""
    files = [
        _gf("tests/step_defs/test_a.py", '@given("the form is visible")\ndef _(): pass'),
        _gf("tests/step_defs/test_b.py", '@then("the form is visible")\ndef _(): pass'),
    ]
    assert validate_no_duplicate_step_definitions(files) == []


def test_string_vs_parse_same_text_no_collision():
    """A bare string and a parsers.parse of the same literal are distinct to pytest-bdd."""
    files = [
        _gf("tests/step_defs/test_a.py", '@when("I click submit")\ndef _(): pass'),
        _gf("tests/step_defs/test_b.py", '@when(parsers.parse("I click submit"))\ndef _(): pass'),
    ]
    # Different parser_type → not a guaranteed collision → not flagged.
    assert validate_no_duplicate_step_definitions(files) == []


def test_parameterised_different_varname_no_collision():
    """{user} vs {username} are different patterns — must not be flagged."""
    files = [
        _gf("tests/step_defs/test_a.py",
            '@when(parsers.parse("I log in as {user}"))\ndef _(): pass'),
        _gf("tests/step_defs/test_b.py",
            '@when(parsers.parse("I log in as {username}"))\ndef _(): pass'),
    ]
    assert validate_no_duplicate_step_definitions(files) == []


def test_duplicate_within_single_file_not_flagged_here():
    """A dup within ONE file is a different problem; this validator is cross-file only."""
    files = [
        _gf("tests/step_defs/test_a.py",
            '@given("x")\ndef _(): pass\n@given("x")\ndef __(): pass'),
    ]
    # Only one file involved → registry maps the key to a single path → no error.
    assert validate_no_duplicate_step_definitions(files) == []


def test_non_stepdef_files_ignored():
    """Page objects / feature files must not be scanned for decorators."""
    files = [
        _gf("pages/login_page.py", '@given("I am on the login page")  # not a real step\ndef _(): pass'),
        _gf("features/login.feature", 'Given I am on the login page'),
        _gf("tests/step_defs/test_a.py", '@given("I am on the login page")\ndef _(): pass'),
    ]
    # Only ONE real step-def file → no cross-file duplicate.
    assert validate_no_duplicate_step_definitions(files) == []


def test_regenerated_reference_not_double_counted(tmp_path):
    """If the batch regenerates a file that also exists on disk, the on-disk copy
    is skipped (superseded) so we don't flag a file as colliding with itself."""
    step_defs = tmp_path / "tests" / "step_defs"
    step_defs.mkdir(parents=True)
    (step_defs / "test_login.py").write_text(
        '@given("I am on the login page")\ndef _(): pass', encoding="utf-8")

    # Same path regenerated in this batch — must NOT collide with the stale disk copy.
    files = [
        _gf("tests/step_defs/test_login.py",
            '@given("I am on the login page")\ndef _(): pass'),
    ]
    assert validate_no_duplicate_step_definitions(files, project_root=tmp_path) == []


def test_empty_input():
    assert validate_no_duplicate_step_definitions([]) == []


def test_no_project_root_still_checks_new_vs_new():
    """Without project_root, new-vs-new collisions are still caught."""
    files = [
        _gf("tests/step_defs/test_a.py", '@given("dup")\ndef _(): pass'),
        _gf("tests/step_defs/test_b.py", '@given("dup")\ndef _(): pass'),
    ]
    assert validate_no_duplicate_step_definitions(files) == []


# ─────────────────────────────────────────────────────────────
# repair_format — repair-loop-targetable error messages
# ─────────────────────────────────────────────────────────────

def test_repair_format_targets_generated_file():
    """repair_format=True must also report nothing — there is nothing to repair."""
    files = [
        _gf("tests/step_defs/test_login_edge.py",
            '@given("I am on the login page")\ndef _(): pass'),
        _gf("tests/step_defs/test_login.py",
            '@given("I am on the login page")\ndef _(): pass'),
    ]
    assert validate_no_duplicate_step_definitions(files, repair_format=True) == []


def test_repair_format_also_reports_nothing():
    """Two modules declaring the same step is the SELF-CONTAINED pattern, not a
    defect, so the repair loop is never invoked for it."""
    files = [
        _gf("tests/step_defs/test_a.py", '@given("dup")\ndef _(): pass'),
        _gf("tests/step_defs/test_b.py", '@given("dup")\ndef _(): pass'),
    ]
    assert validate_no_duplicate_step_definitions(files, repair_format=True) == []