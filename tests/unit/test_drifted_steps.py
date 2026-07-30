"""Tests for drifted-step detection and its repair-feedback wiring.

Pins the fix for a live failure: one step's wording drifted between the
feature file and the step-def file, so the coverage and unused-step
validators fired in opposite directions and the repair oscillated - the
model deleted the decorator to fix "unused", creating "missing coverage",
which re-added it, which was "unused" again. Attempts 3 and 4 undid each
other and the run ended blocked one edit from green.

detect_drifted_steps pairs the two halves deterministically (token
containment in Python, never model judgment) and emits ONE combined
instruction: align the wording.
"""
import pytest

import agents.agent2_coder as agent2
from validators.gherkin_analyzer import (
    _containment,
    _drift_tokens,
    detect_drifted_steps,
)


class _GF:
    def __init__(self, file_path: str, content: str):
        self.file_path = file_path
        self.content = content


def _feature(*steps: str) -> str:
    return "Feature: f\n\n  Scenario: s\n" + "".join(f"    {s}\n" for s in steps)


def _step_defs(*decs) -> str:
    body = "from pytest_bdd import given, when, then, parsers\n\n"
    for i, (kw, phrase) in enumerate(decs):
        body += f'@{kw}("{phrase}")\ndef f{i}(login_page) -> None:\n    pass\n\n'
    return body


def _pairs(ft: str, sd: str):
    errors, phrases = detect_drifted_steps([
        _GF("features/x.feature", ft),
        _GF("tests/step_defs/test_x.py", sd),
    ])
    return errors, phrases


# ── the metric ───────────────────────────────────────────────────────────

def test_containment_chosen_over_jaccard_for_measured_reasons():
    """The production drift EXTENDS a phrase: 100% containment, 57% Jaccard.
    Key-noun substitution (save->cancel) is 60% Jaccard - above any workable
    Jaccard bar - but only 75% containment. Containment separates the two."""
    ext_a = _drift_tokens("I clear the username field and click away")
    ext_b = _drift_tokens("I clear the username field")
    assert _containment(ext_a, ext_b) == 1.0

    sub_a = _drift_tokens("I click the save button")
    sub_b = _drift_tokens("I click the cancel button")
    assert _containment(sub_a, sub_b) < 0.85


# ── positive: drift must be detected ─────────────────────────────────────

def test_extension_drift_is_paired():
    """The exact production case."""
    errors, phrases = _pairs(
        _feature("When I clear the username field and click away"),
        _step_defs(("when", "I clear the username field")),
    )
    assert len(errors) == 1
    assert "make the two phrasings IDENTICAL" in errors[0].replace("\n", " ") \
        or "IDENTICAL" in errors[0]
    assert "I clear the username field" in phrases
    assert "I clear the username field and click away" in phrases


def test_filler_word_drift_is_paired():
    errors, _ = _pairs(
        _feature("When I navigate to the dashboard page"),
        _step_defs(("when", "I navigate dashboard page")),
    )
    assert len(errors) == 1


def test_drift_with_parser_placeholder_is_paired():
    """Placeholders are stripped before comparison, not compared."""
    errors, _ = _pairs(
        _feature('When I enter "admin" into the username field'),
        _step_defs(("when", 'I enter "{value}" in the username field')),
    )
    assert len(errors) == 1


def test_two_independent_drifts_pair_one_to_one():
    errors, _ = _pairs(
        _feature("When I clear the username field and move away",
                 "When I verify the error banner appears and stays"),
        _step_defs(("when", "I clear the username field"),
                   ("when", "I verify the error banner appears")),
    )
    assert len(errors) == 2


def test_one_decorator_explains_at_most_one_step():
    """Greedy 1:1 - a single decorator cannot excuse two missing steps."""
    errors, _ = _pairs(
        _feature("When I clear the username field and move away",
                 "When I clear the username field and click outside"),
        _step_defs(("when", "I clear the username field")),
    )
    assert len(errors) == 1


# ── negative: genuine problems must NOT be paired away ───────────────────

def test_genuinely_different_steps_do_not_pair():
    """Deletion IS the right fix here; drift detection must stay silent."""
    errors, _ = _pairs(
        _feature("When I submit the form"),
        _step_defs(("when", "I log out of the application")),
    )
    assert errors == []


def test_key_noun_substitution_is_not_drift():
    """save vs cancel / username vs password are different steps."""
    for a, b in [("When I click the save button", "I click the cancel button"),
                 ("When I enter the username", "I enter the password")]:
        errors, _ = _pairs(_feature(a), _step_defs(("when", b)))
        assert errors == [], (a, b)


def test_plain_dead_decorator_is_not_paired():
    """All steps covered: the unused decorator is real dead code."""
    errors, _ = _pairs(
        _feature("When I submit the form"),
        _step_defs(("when", "I submit the form"),
                   ("when", "I do something never used")),
    )
    assert errors == []


def test_genuinely_missing_step_is_not_paired():
    """No unused decorator exists: the coverage error must stand alone."""
    errors, _ = _pairs(
        _feature("When I submit the form", "When I check the result"),
        _step_defs(("when", "I submit the form")),
    )
    assert errors == []


def test_empty_phrases_neither_crash_nor_pair():
    errors, _ = _pairs(_feature("When   "), _step_defs(("when", "")))
    assert errors == []


def test_unpaired_step_def_file_is_silent():
    errors, phrases = detect_drifted_steps(
        [_GF("tests/step_defs/test_x.py", _step_defs(("when", "anything")))])
    assert errors == [] and phrases == set()


# ── the wiring: suppression must be exact, never fuzzy ───────────────────

def _collect(ft: str, sd: str):
    return agent2._collect_repairable_errors([
        _GF("features/x.feature", ft),
        _GF("tests/step_defs/test_x.py", sd),
    ])


def _tally(errors):
    return (
        sum("Drifted step wording" in e for e in errors),
        sum("has no matching" in e for e in errors),
        sum("Unused step-definition" in e for e in errors),
    )


def test_drifted_pair_replaces_both_halves():
    errors = _collect(
        _feature("When I clear the username field and click away"),
        _step_defs(("when", "I clear the username field")),
    )
    assert _tally(errors) == (1, 0, 0)


def test_unrelated_missing_step_survives_suppression():
    """The over-suppression bug: fuzzy matching against the drift message
    swallowed genuinely missing steps. Suppression must key on the exact
    drifted phrases only."""
    errors = _collect(
        _feature("When I clear the username field and click away",
                 "When I verify something completely unrelated"),
        _step_defs(("when", "I clear the username field")),
    )
    assert _tally(errors) == (1, 1, 0)


def test_similar_but_different_phrase_survives_suppression():
    """'I clear the password field' shares words with the drifted pair but is
    a different step - its coverage error must not be swallowed."""
    errors = _collect(
        _feature("When I clear the username field and click away",
                 "When I clear the password field"),
        _step_defs(("when", "I clear the username field")),
    )
    counts = _tally(errors)
    assert counts == (1, 1, 0)
    surviving = [e for e in errors if "has no matching" in e]
    assert "password" in surviving[0]


def test_no_drift_leaves_old_behaviour_untouched():
    errors = _collect(
        _feature("When I submit the form"),
        _step_defs(("when", "I log out entirely")),
    )
    assert _tally(errors) == (0, 1, 1)


def test_clean_batch_produces_no_errors():
    errors = _collect(
        _feature("When I submit the form"),
        _step_defs(("when", "I submit the form")),
    )
    assert _tally(errors) == (0, 0, 0)