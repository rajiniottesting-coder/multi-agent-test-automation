"""Unit tests for Phase-2 Tier-2 backlog 2.3 — error-type-aware repair guidance.

  _classify_error(error)              -> class label
  _build_error_type_guidance(errors)  -> targeted, de-duplicated hint block

No Jira / LLM / network. Pure string classification. Verifies each validator
error class maps to the right label and that the guidance block contains only
the hints for classes actually present, in the fixed rule order.
"""
import pytest

from agents.agent2_coder import _classify_error, _build_error_type_guidance


# Real validator error strings (prefixes taken verbatim from the validators).
IMPORT_ERR = "Import resolution error in 'tests/step_defs/test_x.py': cannot import 'pages.ghost'"
METHOD_ERR = "Method resolution error in 'tests/step_defs/test_x.py': login_fast() not on LoginPage"
DUP_ERR = "Duplicate step-definition error in 'tests/step_defs/test_y.py': step already defined"
STEP_ERR = "Step coverage error in 'tests/step_defs/test_z.py': feature step `I wait` has no matching @when()"
GHERKIN_ERR = "Gherkin structure error in 'features/a.feature': step on line 4 is malformed"
FILENAME_ERR = "Filename consistency error: step def 'x' references 'login' but is named test_cart"
NOVEL_ERR = "Some totally novel error string"


@pytest.mark.parametrize("err,label", [
    (IMPORT_ERR, "import_resolution"),
    (METHOD_ERR, "method_resolution"),
    (DUP_ERR, "duplicate_step"),
    (STEP_ERR, "step_coverage"),
    (GHERKIN_ERR, "gherkin_structure"),
    (FILENAME_ERR, "filename_consistency"),
    (NOVEL_ERR, "other"),
])
def test_classify_each_error_class(err, label):
    assert _classify_error(err) == label


def test_empty_errors_returns_empty_string():
    assert _build_error_type_guidance([]) == ""


def test_guidance_contains_only_present_classes():
    g = _build_error_type_guidance([IMPORT_ERR, METHOD_ERR])
    assert "BROKEN IMPORT" in g
    assert "UNKNOWN PAGE METHOD" in g
    assert "MISSING STEP DEFINITION" not in g
    assert "DUPLICATE STEP DEFINITION" not in g


def test_guidance_deduplicates_repeated_class():
    g = _build_error_type_guidance([STEP_ERR, STEP_ERR, STEP_ERR])
    assert g.count("MISSING STEP DEFINITION") == 1


def test_guidance_follows_fixed_rule_order():
    # duplicate_step precedes import_resolution in the rule list, regardless of
    # the order the errors arrive.
    g = _build_error_type_guidance([IMPORT_ERR, DUP_ERR])
    assert g.index("DUPLICATE STEP DEFINITION") < g.index("BROKEN IMPORT")


def test_unknown_only_yields_fallback():
    g = _build_error_type_guidance([NOVEL_ERR])
    assert "Address the validator message" in g


def test_known_plus_unknown_appends_fallback_once():
    g = _build_error_type_guidance([STEP_ERR, NOVEL_ERR])
    assert "MISSING STEP DEFINITION" in g
    assert g.count("Address the validator message") == 1


def test_step_coverage_hint_is_step_specific_not_generic():
    # Regression guard for the whole point of 2.3: an import error must NOT be
    # answered with "add a @given/@when/@then decorator".
    g = _build_error_type_guidance([IMPORT_ERR])
    assert "decorator" not in g.lower()