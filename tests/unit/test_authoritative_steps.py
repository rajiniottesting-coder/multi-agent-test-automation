"""Tests for the authoritative step list injected into step-def generation.

Pins the fix for first-attempt validator storms (25-27 coverage/unused errors
before any repair ran). The feature file and its step-def file are generated
in separate LLM calls; previously the step-def call received only the raw
test cases, so the model re-derived every Gherkin phrase independently and
each wording difference became a coverage error plus an unused-step error.

The block is built with _extract_feature_steps - the same function the
coverage validator uses - so what the model is told to implement and what the
validator will demand are the same set by construction.
"""
import re

from agents.agent2_coder import (
    _SUBSTITUTED_PLACEHOLDERS,
    _build_authoritative_steps_block,
)
from config.paths import PROMPTS_DIR


class _FP:
    def __init__(self, file_path: str, file_type: str):
        self.file_path = file_path
        self.file_type = file_type


class _GF:
    def __init__(self, file_path: str, content: str):
        self.file_path = file_path
        self.content = content


_FEATURE = """Feature: Password validation

  Background:
    Given I am logged in as "admin"

  Scenario: too short
    When I enter "abc" in the password field
    Then I should see the length error

  Scenario: mismatch
    When I enter "abc" in the password field
    And I enter "xyz" in the confirm password field
    Then I should see the mismatch error
"""


def _step_lines(block: str):
    return re.findall(r"^\s*\d+\. \[\w+\] (.+)$", block, re.M)


# ── positive: the block is built and complete ────────────────────────────

def test_stem_matched_feature_builds_the_block():
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_password_validation.py", "step_definitions"),
        [_GF("features/password_validation.feature", _FEATURE)],
    )
    assert "AUTHORITATIVE STEP LIST" in block
    assert "features/password_validation.feature" in block


def test_every_unique_step_is_listed_once():
    """6 raw steps, one duplicated across scenarios -> 5 unique entries."""
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_password_validation.py", "step_definitions"),
        [_GF("features/password_validation.feature", _FEATURE)],
    )
    steps = _step_lines(block)
    assert len(steps) == 5
    assert steps.count('I enter "abc" in the password field') == 1


def test_background_and_quoted_value_steps_are_included():
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_password_validation.py", "step_definitions"),
        [_GF("features/password_validation.feature", _FEATURE)],
    )
    listed = _step_lines(block)
    assert 'I am logged in as "admin"' in listed
    assert 'I enter "xyz" in the confirm password field' in listed


def test_single_feature_fallback_when_stems_differ():
    """Plans overwhelmingly generate one feature; a stem mismatch must not
    silently drop the contract."""
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_add_user.py", "step_definitions"),
        [_GF("features/password_rules.feature", _FEATURE)],
    )
    assert block != ""


def test_stem_match_wins_over_other_features():
    other = "Feature: b\n\n  Scenario: s\n    Given something else entirely\n"
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_a.py", "step_definitions"),
        [_GF("features/a.feature", _FEATURE), _GF("features/b.feature", other)],
    )
    assert "password field" in block
    assert "something else entirely" not in block


def test_verbatim_instruction_is_present():
    """The instruction wording is the contract; guard its key phrases."""
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_password_validation.py", "step_definitions"),
        [_GF("features/password_validation.feature", _FEATURE)],
    )
    assert "VERBATIM" in block
    assert "Do NOT invent decorators" in block


# ── negative: no block is better than a wrong block ──────────────────────

def test_non_step_def_files_get_no_block():
    for ftype in ("page_object", "feature", "other"):
        block = _build_authoritative_steps_block(
            _FP("pages/x_page.py", ftype),
            [_GF("features/x.feature", _FEATURE)],
        )
        assert block == "", ftype


def test_no_feature_in_batch_yields_empty():
    """Update-mode single-file regeneration has no feature in the batch."""
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_x.py", "step_definitions"),
        [_GF("pages/x_page.py", "class XPage:\n    pass\n")],
    )
    assert block == ""


def test_ambiguous_features_yield_empty_rather_than_a_guess():
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_x.py", "step_definitions"),
        [_GF("features/a.feature", _FEATURE), _GF("features/b.feature", _FEATURE)],
    )
    assert block == ""


def test_feature_without_steps_yields_empty():
    block = _build_authoritative_steps_block(
        _FP("tests/step_defs/test_x.py", "step_definitions"),
        [_GF("features/x.feature", "Feature: empty\n")],
    )
    assert block == ""


def test_empty_batch_yields_empty():
    assert _build_authoritative_steps_block(
        _FP("tests/step_defs/test_x.py", "step_definitions"), []) == ""


# ── wiring invariants ────────────────────────────────────────────────────

def test_placeholder_is_declared_for_the_cache_leak_check():
    assert "{authoritative_steps_block}" in _SUBSTITUTED_PLACEHOLDERS


def test_placeholder_sits_above_the_cache_marker():
    """Per-call content below the marker would change the cached prefix on
    every call - each call pays the write premium and no read ever hits."""
    template = (PROMPTS_DIR / "agent2_coder_generate.md").read_text(encoding="utf-8")
    marker = "<!-- ===== CACHE BREAKPOINT"
    assert template.index("{authoritative_steps_block}") < template.index(marker)

# =========================================================================
# THE AUTHORITATIVE STEP LIST MUST DEMAND WHAT THE VALIDATOR DEMANDS
#
# _build_authoritative_steps_block tells the model the feature "contains
# EXACTLY these unique steps" and that it must NOT write decorators for
# anything absent from the list. That makes the list stronger than any
# guidance: whatever it omits, the model is forbidden to add.
#
# It de-duplicated on the PHRASE. A feature using one phrase as both a Given
# and a When listed only the first, so the model was forbidden from writing
# the very step the coverage validator then demanded. Four repair attempts
# could not resolve it - there was no output satisfying both.
#
# Its own docstring claimed the guarantee this test now enforces:
#
#     "What the model is told to implement and what the validator will
#      demand are therefore the same set by construction, not by hope."
#
# It was hope. The extraction was shared; the de-duplication was not.
# =========================================================================

def _steps_listed_for_the_model(block: str) -> set:
    """The (keyword, phrase) pairs the injected block actually offers."""
    listed = set()
    for line in block.splitlines():
        text = line.strip()
        if not text or not text[0].isdigit() or "] " not in text:
            continue
        if "[" not in text or text.count("[") != 1:
            continue
        keyword = text.split("[", 1)[1].split("]", 1)[0]
        if keyword not in ("given", "when", "then"):
            continue
        listed.add((keyword, text.split("] ", 1)[1].strip()))
    return listed


def test_the_injected_step_list_offers_every_pair_the_validator_demands():
    """One phrase under two keywords is TWO steps, and both must be listed."""
    import textwrap
    from types import SimpleNamespace

    from agents.agent2_coder import _build_authoritative_steps_block
    from validators.gherkin_analyzer import _extract_feature_steps

    feature = SimpleNamespace(
        file_path="features/thing.feature",
        content=textwrap.dedent('''
            Feature: Thing

              Scenario: One
                Given I open the listing
                When I do something

              Scenario: Two
                When I open the listing
                Then something happened
        '''))
    plan = SimpleNamespace(file_type="step_definitions",
                           file_path="tests/step_defs/test_thing.py")

    demanded = {(k, p.strip()) for k, p in _extract_feature_steps(feature.content)}
    listed = _steps_listed_for_the_model(
        _build_authoritative_steps_block(plan, [feature]))

    missing = demanded - listed
    assert not missing, (
        f"the validator demands {sorted(missing)} and the injected list does "
        f"not offer it. The block tells the model not to write decorators for "
        f"anything absent from the list, so this is not an omission - it is a "
        f"prohibition on satisfying the gate."
    )


def test_a_repeated_step_under_ONE_keyword_is_still_listed_once():
    """Break the thing the guard guards.

    Keying on (keyword, phrase) must not stop collapsing genuine repeats. The
    same Given in three scenarios is one decorator, and listing it three times
    would invite three.
    """
    import textwrap
    from types import SimpleNamespace

    from agents.agent2_coder import _build_authoritative_steps_block

    feature = SimpleNamespace(
        file_path="features/thing.feature",
        content=textwrap.dedent('''
            Feature: Thing

              Scenario: One
                Given I am signed in
                Then something happened

              Scenario: Two
                Given I am signed in
                Then something else happened
        '''))
    plan = SimpleNamespace(file_type="step_definitions",
                           file_path="tests/step_defs/test_thing.py")

    listed = _steps_listed_for_the_model(
        _build_authoritative_steps_block(plan, [feature]))
    signed_in = [pair for pair in listed if pair[1] == "I am signed in"]
    assert len(signed_in) == 1, f"listed {len(signed_in)} times, expected once"


def test_the_list_tells_the_model_how_to_serve_two_keywords():
    """Listing both pairs is not enough - the answer looks like a duplicate,
    and a model avoiding duplicates will not reach for it unaided."""
    import textwrap
    from types import SimpleNamespace

    from agents.agent2_coder import _build_authoritative_steps_block

    feature = SimpleNamespace(
        file_path="features/thing.feature",
        content=textwrap.dedent('''
            Feature: Thing

              Scenario: One
                Given I open the listing
                Then something happened
        '''))
    plan = SimpleNamespace(file_type="step_definitions",
                           file_path="tests/step_defs/test_thing.py")
    block = _build_authoritative_steps_block(plan, [feature])

    assert "BOTH decorators" in block, "say that two keywords need two decorators"
    assert "@given(" in block and "@when(" in block, "show the stacked form"