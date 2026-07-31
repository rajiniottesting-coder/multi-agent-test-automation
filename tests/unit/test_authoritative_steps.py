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