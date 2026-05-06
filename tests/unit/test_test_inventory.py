"""
Unit tests for agents.test_inventory module.

Run with:
    python -m pytest tests/unit/test_test_inventory.py -v

These tests use temporary directories created by pytest's `tmp_path` fixture,
so they don't touch the real features/ directory. They run fast and are
fully isolated.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agents.test_inventory import (
    _parse_feature_file,
    filter_duplicate_test_cases,
    find_matching_scenario,
    normalize_scenario_name,
    scan_features_dir,
    validate_filename_consistency,
)


# ─── normalize_scenario_name ────────────────────────────────────────────


class TestNormalizeScenarioName:
    """Normalization is the foundation of matching — it must be consistent."""

    def test_lowercases_input(self):
        assert normalize_scenario_name("HELLO World") == "hello world"

    def test_strips_leading_and_trailing_whitespace(self):
        assert normalize_scenario_name("  hello world  ") == "hello world"

    def test_collapses_internal_whitespace(self):
        assert normalize_scenario_name("hello    world") == "hello world"

    def test_collapses_tabs_and_newlines(self):
        # Tabs and newlines should be treated as single-space separators
        assert normalize_scenario_name("hello\tworld\nfoo") == "hello world foo"

    def test_handles_empty_string(self):
        assert normalize_scenario_name("") == ""

    def test_handles_whitespace_only(self):
        assert normalize_scenario_name("   \t\n  ") == ""

    def test_preserves_punctuation(self):
        # Punctuation should be kept — "Login: success" != "Login success"
        # in semantic terms, even if a human might consider them equivalent.
        # Conservative matching is the design choice.
        assert normalize_scenario_name("Login: Success!") == "login: success!"

    def test_idempotent(self):
        # Normalizing twice should give the same result as once
        once = normalize_scenario_name("  Hello   World  ")
        twice = normalize_scenario_name(once)
        assert once == twice == "hello world"


# ─── _parse_feature_file ────────────────────────────────────────────────


class TestParseFeatureFile:
    """Parsing extracts only scenario titles, not Background/Feature/comments."""

    def test_simple_feature_with_one_scenario(self, tmp_path: Path):
        feature_file = tmp_path / "simple.feature"
        feature_file.write_text(
            "Feature: Simple test\n"
            "  Scenario: One scenario here\n"
            "    Given something\n"
            "    Then something else\n"
        )
        assert _parse_feature_file(feature_file) == ["One scenario here"]

    def test_multiple_scenarios(self, tmp_path: Path):
        feature_file = tmp_path / "multi.feature"
        feature_file.write_text(
            "Feature: Multi\n"
            "  Scenario: First scenario\n"
            "    Given a\n"
            "  Scenario: Second scenario\n"
            "    Given b\n"
            "  Scenario: Third scenario\n"
            "    Given c\n"
        )
        assert _parse_feature_file(feature_file) == [
            "First scenario",
            "Second scenario",
            "Third scenario",
        ]

    def test_scenario_outline_is_captured(self, tmp_path: Path):
        # Scenario Outline is a parameterized scenario — also a real test.
        feature_file = tmp_path / "outline.feature"
        feature_file.write_text(
            "Feature: With outline\n"
            "  Scenario Outline: Parameterized test\n"
            "    Given <input>\n"
            "    Examples:\n"
            "      | input |\n"
            "      | a     |\n"
            "      | b     |\n"
        )
        assert _parse_feature_file(feature_file) == ["Parameterized test"]

    def test_mixed_scenario_and_outline(self, tmp_path: Path):
        feature_file = tmp_path / "mixed.feature"
        feature_file.write_text(
            "Feature: Mixed\n"
            "  Scenario: Plain scenario\n"
            "    Given x\n"
            "  Scenario Outline: Outline scenario\n"
            "    Given <y>\n"
            "    Examples:\n"
            "      | y |\n"
            "      | 1 |\n"
        )
        # Plain scenarios come first (matched by _SCENARIO_PATTERN),
        # then outlines (matched by _SCENARIO_OUTLINE_PATTERN).
        result = _parse_feature_file(feature_file)
        assert "Plain scenario" in result
        assert "Outline scenario" in result
        assert len(result) == 2

    def test_background_block_not_extracted(self, tmp_path: Path):
        # `Background:` blocks contain Given/When/Then steps that apply to
        # all scenarios but are NOT themselves scenarios. They should be
        # ignored by the parser.
        feature_file = tmp_path / "with_background.feature"
        feature_file.write_text(
            "Feature: With background\n"
            "  Background:\n"
            "    Given I am logged in\n"
            "  Scenario: Real scenario\n"
            "    When I click foo\n"
        )
        assert _parse_feature_file(feature_file) == ["Real scenario"]

    def test_feature_description_not_extracted(self, tmp_path: Path):
        # The "As a / I want / So that" description after Feature: is
        # narrative, not a scenario.
        feature_file = tmp_path / "described.feature"
        feature_file.write_text(
            "Feature: User Login\n"
            "  As a registered user\n"
            "  I want to log in\n"
            "  So that I can access the app\n"
            "\n"
            "  Scenario: Real test\n"
            "    Given x\n"
        )
        assert _parse_feature_file(feature_file) == ["Real test"]

    def test_tags_above_scenarios_ignored(self, tmp_path: Path):
        feature_file = tmp_path / "tagged.feature"
        feature_file.write_text(
            "Feature: Tagged\n"
            "  @smoke @critical\n"
            "  Scenario: Tagged scenario\n"
            "    Given y\n"
        )
        assert _parse_feature_file(feature_file) == ["Tagged scenario"]

    def test_comments_ignored(self, tmp_path: Path):
        feature_file = tmp_path / "commented.feature"
        feature_file.write_text(
            "# This is a comment\n"
            "Feature: Commented\n"
            "  # Another comment\n"
            "  Scenario: Real one\n"
            "    Given z\n"
            "  # Scenario: Fake (in a comment, should be ignored)\n"
        )
        assert _parse_feature_file(feature_file) == ["Real one"]

    def test_indentation_variations(self, tmp_path: Path):
        # Different indentation should still match (real-world LLM output
        # may use 2 or 4 spaces).
        feature_file = tmp_path / "indented.feature"
        feature_file.write_text(
            "Feature: Mixed indent\n"
            "  Scenario: Two-space indent\n"
            "      Given x\n"
            "    Scenario: Four-space indent\n"
            "        Given y\n"
            "Scenario: No indent\n"
            "  Given z\n"
        )
        result = _parse_feature_file(feature_file)
        assert "Two-space indent" in result
        assert "Four-space indent" in result
        assert "No indent" in result

    def test_empty_file(self, tmp_path: Path):
        feature_file = tmp_path / "empty.feature"
        feature_file.write_text("")
        assert _parse_feature_file(feature_file) == []

    def test_feature_with_no_scenarios(self, tmp_path: Path):
        feature_file = tmp_path / "no_scenarios.feature"
        feature_file.write_text(
            "Feature: Documentation only\n"
            "  As a user\n"
            "  I want this\n"
        )
        assert _parse_feature_file(feature_file) == []

    def test_real_world_login_feature(self, tmp_path: Path):
        # Use the EXACT structure of our existing login.feature to ensure
        # this parser handles real production input correctly.
        feature_file = tmp_path / "login.feature"
        feature_file.write_text(
            "Feature: User Login\n"
            "  As a registered user of SauceDemo\n"
            "  I want to log in with my credentials\n"
            "  So that I can access the products inventory page\n"
            "\n"
            "  Background:\n"
            "    Given I am on the SauceDemo login page\n"
            "\n"
            "  @smoke @login\n"
            "  Scenario: Successful login with standard user credentials\n"
            "    When I log in with username \"standard_user\" and password \"secret_sauce\"\n"
            "    Then I should be redirected to the inventory page\n"
            "    And I should see the page title \"Products\"\n"
            "\n"
            "  @login\n"
            "  Scenario: Login fails with invalid password\n"
            "    When I log in with username \"standard_user\" and password \"wrong_password\"\n"
            "    Then I should see the error message \"...\"\n"
            "\n"
            "  @login\n"
            "  Scenario: Login fails for locked-out user\n"
            "    When I log in with username \"locked_out_user\" and password \"secret_sauce\"\n"
            "    Then I should see the error message \"...\"\n"
        )
        result = _parse_feature_file(feature_file)
        assert result == [
            "Successful login with standard user credentials",
            "Login fails with invalid password",
            "Login fails for locked-out user",
        ]


# ─── scan_features_dir ──────────────────────────────────────────────────


class TestScanFeaturesDir:
    """Directory-level scanning: aggregates scenarios across files."""

    def test_empty_directory(self, tmp_path: Path):
        result = scan_features_dir(tmp_path)
        assert result == {
            "files": [],
            "scenarios_by_file": {},
            "all_scenarios": [],
        }

    def test_nonexistent_directory(self, tmp_path: Path):
        nonexistent = tmp_path / "does_not_exist"
        result = scan_features_dir(nonexistent)
        assert result == {
            "files": [],
            "scenarios_by_file": {},
            "all_scenarios": [],
        }

    def test_path_is_a_file_not_directory(self, tmp_path: Path):
        not_a_dir = tmp_path / "oops.feature"
        not_a_dir.write_text("Feature: oops\n")
        result = scan_features_dir(not_a_dir)
        assert result["files"] == []

    def test_directory_with_one_feature_file(self, tmp_path: Path):
        (tmp_path / "login.feature").write_text(
            "Feature: Login\n"
            "  Scenario: One\n"
            "    Given x\n"
            "  Scenario: Two\n"
            "    Given y\n"
        )
        result = scan_features_dir(tmp_path)
        assert result["files"] == ["login.feature"]
        assert result["scenarios_by_file"] == {"login.feature": ["One", "Two"]}
        assert result["all_scenarios"] == ["One", "Two"]

    def test_directory_with_multiple_feature_files(self, tmp_path: Path):
        (tmp_path / "login.feature").write_text(
            "Feature: Login\n"
            "  Scenario: A\n"
        )
        (tmp_path / "checkout.feature").write_text(
            "Feature: Checkout\n"
            "  Scenario: B\n"
            "  Scenario: C\n"
        )
        result = scan_features_dir(tmp_path)
        # Files should be sorted alphabetically for determinism
        assert result["files"] == ["checkout.feature", "login.feature"]
        assert result["scenarios_by_file"]["login.feature"] == ["A"]
        assert result["scenarios_by_file"]["checkout.feature"] == ["B", "C"]
        assert set(result["all_scenarios"]) == {"A", "B", "C"}

    def test_non_feature_files_ignored(self, tmp_path: Path):
        (tmp_path / "login.feature").write_text(
            "Feature: Login\n  Scenario: Only me\n"
        )
        (tmp_path / "README.md").write_text("# Docs")
        (tmp_path / ".gitkeep").write_text("")
        (tmp_path / "config.yaml").write_text("foo: bar")
        result = scan_features_dir(tmp_path)
        assert result["files"] == ["login.feature"]
        assert result["all_scenarios"] == ["Only me"]

    def test_subdirectories_not_recursed(self, tmp_path: Path):
        (tmp_path / "login.feature").write_text(
            "Feature: Top\n  Scenario: At top\n"
        )
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.feature").write_text(
            "Feature: Nested\n  Scenario: Should be ignored\n"
        )
        result = scan_features_dir(tmp_path)
        assert result["files"] == ["login.feature"]
        assert "Should be ignored" not in result["all_scenarios"]


# ─── find_matching_scenario ─────────────────────────────────────────────


class TestFindMatchingScenario:
    """The decision point: 'is this test case already covered?'"""

    @pytest.fixture
    def populated_inventory(self) -> dict:
        return {
            "files": ["login.feature", "checkout.feature"],
            "scenarios_by_file": {
                "login.feature": [
                    "Successful login with standard user",
                    "Login fails for locked-out user",
                ],
                "checkout.feature": [
                    "Add item to cart and checkout",
                ],
            },
            "all_scenarios": [
                "Successful login with standard user",
                "Login fails for locked-out user",
                "Add item to cart and checkout",
            ],
        }

    def test_exact_match_found(self, populated_inventory):
        match = find_matching_scenario(
            "Successful login with standard user", populated_inventory
        )
        assert match is not None
        assert match["file"] == "login.feature"
        assert match["scenario"] == "Successful login with standard user"
        assert match["match_type"] == "exact"

    def test_case_insensitive_match(self, populated_inventory):
        match = find_matching_scenario(
            "SUCCESSFUL LOGIN WITH STANDARD USER", populated_inventory
        )
        assert match is not None
        assert match["file"] == "login.feature"

    def test_whitespace_insensitive_match(self, populated_inventory):
        match = find_matching_scenario(
            "  Successful   login  with standard user  ", populated_inventory
        )
        assert match is not None

    def test_no_match_returns_none(self, populated_inventory):
        match = find_matching_scenario(
            "A completely new test case that doesn't exist", populated_inventory
        )
        assert match is None

    def test_partial_match_does_NOT_count(self, populated_inventory):
        match = find_matching_scenario("Login", populated_inventory)
        assert match is None

    def test_empty_test_case_returns_none(self, populated_inventory):
        assert find_matching_scenario("", populated_inventory) is None
        assert find_matching_scenario("   ", populated_inventory) is None

    def test_empty_inventory_returns_none(self):
        empty = {"files": [], "scenarios_by_file": {}, "all_scenarios": []}
        match = find_matching_scenario("anything", empty)
        assert match is None

    def test_match_returns_correct_file_when_multiple_files(
        self, populated_inventory
    ):
        match = find_matching_scenario(
            "Add item to cart and checkout", populated_inventory
        )
        assert match["file"] == "checkout.feature"

    def test_returns_original_scenario_text_not_normalized(
        self, populated_inventory
    ):
        match = find_matching_scenario(
            "successful login with standard user", populated_inventory
        )
        assert match["scenario"] == "Successful login with standard user"


# ─── filter_duplicate_test_cases ────────────────────────────────────────


class TestFilterDuplicateTestCases:
    """The partition logic Agent 2 uses to decide what work needs doing."""

    @pytest.fixture
    def inventory_with_login(self) -> dict:
        return {
            "files": ["login.feature"],
            "scenarios_by_file": {
                "login.feature": [
                    "Successful login with standard user",
                    "Login fails for locked-out user",
                    "Login fails with invalid password",
                ],
            },
            "all_scenarios": [
                "Successful login with standard user",
                "Login fails for locked-out user",
                "Login fails with invalid password",
            ],
        }

    @pytest.fixture
    def empty_inventory(self) -> dict:
        return {"files": [], "scenarios_by_file": {}, "all_scenarios": []}

    def _tc(self, key: str, summary: str, description: str = "") -> dict:
        return {"key": key, "summary": summary, "description": description}

    def test_all_test_cases_are_new(self, empty_inventory):
        test_cases = [
            self._tc("SCRUM-9", "Brand new test 1"),
            self._tc("SCRUM-10", "Brand new test 2"),
        ]
        new, skipped = filter_duplicate_test_cases(test_cases, empty_inventory)
        assert len(new) == 2
        assert len(skipped) == 0
        assert new == test_cases

    def test_all_test_cases_are_duplicates(self, inventory_with_login):
        test_cases = [
            self._tc("SCRUM-9", "Successful login with standard user"),
            self._tc("SCRUM-10", "Login fails for locked-out user"),
        ]
        new, skipped = filter_duplicate_test_cases(test_cases, inventory_with_login)
        assert len(new) == 0
        assert len(skipped) == 2
        assert skipped[0]["matched_file"] == "login.feature"
        assert skipped[0]["matched_scenario"] == "Successful login with standard user"
        assert skipped[0]["test_case"]["key"] == "SCRUM-9"

    def test_mix_of_new_and_duplicate(self, inventory_with_login):
        test_cases = [
            self._tc("SCRUM-9", "Successful login with standard user"),  # duplicate
            self._tc("SCRUM-10", "Login with empty username"),           # new
            self._tc("SCRUM-11", "Login fails for locked-out user"),     # duplicate
            self._tc("SCRUM-12", "Login with empty password"),           # new
        ]
        new, skipped = filter_duplicate_test_cases(test_cases, inventory_with_login)
        assert len(new) == 2
        assert len(skipped) == 2
        new_keys = {tc["key"] for tc in new}
        skipped_keys = {s["test_case"]["key"] for s in skipped}
        assert new_keys == {"SCRUM-10", "SCRUM-12"}
        assert skipped_keys == {"SCRUM-9", "SCRUM-11"}

    def test_empty_test_cases_list(self, inventory_with_login):
        new, skipped = filter_duplicate_test_cases([], inventory_with_login)
        assert new == []
        assert skipped == []

    def test_test_case_with_no_summary_treated_as_new(self, inventory_with_login):
        # Defensive: malformed test case should not crash, treated as "new"
        test_cases = [
            self._tc("SCRUM-99", ""),  # empty summary
            {"key": "SCRUM-100", "description": "no summary key"},
        ]
        new, skipped = filter_duplicate_test_cases(test_cases, inventory_with_login)
        assert len(new) == 2
        assert len(skipped) == 0

    def test_case_insensitive_dedup(self, inventory_with_login):
        test_cases = [
            self._tc("SCRUM-9", "SUCCESSFUL LOGIN WITH STANDARD USER"),
            self._tc("SCRUM-10", "successful login with standard user"),
        ]
        new, skipped = filter_duplicate_test_cases(test_cases, inventory_with_login)
        assert len(new) == 0
        assert len(skipped) == 2

    def test_whitespace_insensitive_dedup(self, inventory_with_login):
        test_cases = [
            self._tc("SCRUM-9", "  Successful   login with standard user  "),
        ]
        new, skipped = filter_duplicate_test_cases(test_cases, inventory_with_login)
        assert len(new) == 0
        assert len(skipped) == 1

    def test_skipped_records_preserve_original_test_case(self, inventory_with_login):
        original = self._tc(
            "SCRUM-9",
            "Successful login with standard user",
            description="A detailed description with multiple lines\nand bullet points",
        )
        new, skipped = filter_duplicate_test_cases([original], inventory_with_login)
        assert len(skipped) == 1
        assert skipped[0]["test_case"] == original
        assert skipped[0]["test_case"]["description"] == original["description"]

    def test_preserves_input_order(self, inventory_with_login):
        test_cases = [
            self._tc("SCRUM-A", "Successful login with standard user"),  # dup
            self._tc("SCRUM-B", "Brand new 1"),                           # new
            self._tc("SCRUM-C", "Login fails for locked-out user"),       # dup
            self._tc("SCRUM-D", "Brand new 2"),                           # new
        ]
        new, skipped = filter_duplicate_test_cases(test_cases, inventory_with_login)
        assert [tc["key"] for tc in new] == ["SCRUM-B", "SCRUM-D"]
        assert [s["test_case"]["key"] for s in skipped] == ["SCRUM-A", "SCRUM-C"]


# ─── validate_filename_consistency ──────────────────────────────────────


class TestValidateFilenameConsistency:
    """Catches LLM drift between feature filenames and step def references."""

    def _make_file(self, path: str, content: str = ""):
        """Build a duck-typed object that looks like a GeneratedFile."""
        class _Stub:
            pass
        s = _Stub()
        s.file_path = path
        s.content = content
        return s

    def test_empty_batch_no_errors(self):
        assert validate_filename_consistency([]) == []

    def test_consistent_batch_no_errors(self):
        files = [
            self._make_file(
                "features/login_validation.feature",
                "Feature: Login\n  Scenario: x\n",
            ),
            self._make_file(
                "tests/step_defs/test_login_validation.py",
                'from config.paths import feature_path\n'
                'scenarios(str(feature_path("login_validation")))\n',
            ),
        ]
        assert validate_filename_consistency(files) == []

    def test_kebab_vs_snake_mismatch_autocorrected(self):
        """Phase 7: kebab-vs-snake mismatch is now auto-corrected, not erored.
        This was the original PR #7 bug. With auto-correction, the validator
        rewrites the step def's content in place to match the feature filename."""
        files = [
            self._make_file(
                "features/login_validation.feature",  # snake
                "Feature: Login validation\n",
            ),
            self._make_file(
                "tests/step_defs/test_login_validation.py",
                'scenarios(str(feature_path("login-validation")))\n',  # kebab — wrong
            ),
        ]
        errors = validate_filename_consistency(files)
        # No error — should auto-correct
        assert errors == []
        # Step def content should be rewritten with the snake form
        assert 'feature_path("login_validation")' in files[1].content
        assert 'feature_path("login-validation")' not in files[1].content

    def test_snake_to_kebab_autocorrected(self):
        """Reverse direction: feature is kebab, step def uses snake. Same fix applies."""
        files = [
            self._make_file(
                "features/login-validation.feature",  # kebab
                "Feature: Login validation\n",
            ),
            self._make_file(
                "tests/step_defs/test_login_validation.py",
                'scenarios(str(feature_path("login_validation")))\n',  # snake — wrong
            ),
        ]
        errors = validate_filename_consistency(files)
        assert errors == []
        assert 'feature_path("login-validation")' in files[1].content

    def test_unambiguous_correction_with_multiple_features(self):
        """Even when multiple feature files exist in the batch, an unambiguous
        single-match correction should still apply."""
        files = [
            self._make_file(
                "features/login_validation.feature",
                "Feature: A\n",
            ),
            self._make_file(
                "features/cart_checkout.feature",
                "Feature: B\n",
            ),
            self._make_file(
                "tests/step_defs/test_login_validation.py",
                'scenarios(str(feature_path("login-validation")))\n',  # kebab variant of login_validation
            ),
        ]
        errors = validate_filename_consistency(files)
        # Should auto-correct because only login_validation matches when normalized
        assert errors == []
        assert 'feature_path("login_validation")' in files[2].content

    def test_single_quotes_also_autocorrected(self):
        """LLMs sometimes use single quotes. Auto-correction must handle both."""
        files = [
            self._make_file(
                "features/login_validation.feature",
                "Feature: x\n",
            ),
            self._make_file(
                "tests/step_defs/test_login_validation.py",
                "scenarios(str(feature_path('login-validation')))\n",  # single quotes!
            ),
        ]
        errors = validate_filename_consistency(files)
        assert errors == []
        # The fix should use single quotes since that's what was there
        assert "feature_path('login_validation')" in files[1].content

    def test_completely_missing_feature_caught(self):
        """When the referenced feature doesn't exist AT ALL (not even via separator
        normalization), this is a genuine bug and we still hard-fail."""
        files = [
            self._make_file(
                "tests/step_defs/test_orphan.py",
                'scenarios(str(feature_path("orphan")))\n',
            ),
        ]
        errors = validate_filename_consistency(files)
        assert len(errors) == 1
        assert "orphan" in errors[0]

    def test_camelcase_not_autocorrected(self):
        """We only auto-correct separator-style mismatches. CamelCase or other
        styles are NOT guessed at — they hard-fail to alert the human."""
        files = [
            self._make_file(
                "features/login_validation.feature",
                "Feature: x\n",
            ),
            self._make_file(
                "tests/step_defs/test_login_validation.py",
                'scenarios(str(feature_path("LoginValidation")))\n',  # camel
            ),
        ]
        errors = validate_filename_consistency(files)
        # Camel doesn't normalize the same way — should NOT auto-correct
        assert len(errors) == 1
        assert "LoginValidation" in errors[0]

    def test_totally_unrelated_name_not_autocorrected(self):
        """Auto-correction should never guess between semantically different names."""
        files = [
            self._make_file(
                "features/login_validation.feature",
                "Feature: x\n",
            ),
            self._make_file(
                "tests/step_defs/test_login_validation.py",
                'scenarios(str(feature_path("checkout")))\n',  # totally different
            ),
        ]
        errors = validate_filename_consistency(files)
        # Should NOT auto-correct — alert the human
        assert len(errors) == 1
        assert "checkout" in errors[0]

    def test_step_def_without_feature_path_call_ignored(self):
        files = [
            self._make_file(
                "tests/step_defs/test_helper.py",
                'def some_helper(): pass\n',
            ),
        ]
        assert validate_filename_consistency(files) == []

    def test_multiple_feature_path_calls_in_one_file(self):
        files = [
            self._make_file(
                "features/login.feature", "Feature: Login\n"
            ),
            self._make_file(
                "tests/step_defs/test_combined.py",
                'scenarios(str(feature_path("login")))\n'
                'scenarios(str(feature_path("missing_one")))\n',
            ),
        ]
        errors = validate_filename_consistency(files)
        assert len(errors) == 1
        assert "missing_one" in errors[0]

    def test_double_quotes_and_single_quotes_both_handled(self):
        files = [
            self._make_file(
                "features/cart.feature", "Feature: Cart\n"
            ),
            self._make_file(
                "tests/step_defs/test_cart.py",
                "scenarios(str(feature_path('cart')))\n",
            ),
        ]
        assert validate_filename_consistency(files) == []

    def test_non_python_file_ignored(self):
        files = [
            self._make_file(
                "README.md",
                'Use feature_path("nonexistent") in your step defs.\n',
            ),
        ]
        assert validate_filename_consistency(files) == []

    def test_python_file_outside_step_defs_ignored(self):
        files = [
            self._make_file(
                "pages/some_page.py",
                'feature_path("nonexistent")\n',
            ),
        ]
        assert validate_filename_consistency(files) == []

    def test_multiple_files_multiple_errors(self):
        files = [
            self._make_file("features/a.feature", "Feature: A\n"),
            self._make_file(
                "tests/step_defs/test_one.py",
                'scenarios(str(feature_path("a")))\n',
            ),
            self._make_file(
                "tests/step_defs/test_two.py",
                'scenarios(str(feature_path("missing_b")))\n',
            ),
            self._make_file(
                "tests/step_defs/test_three.py",
                'scenarios(str(feature_path("missing_c")))\n',
            ),
        ]
        errors = validate_filename_consistency(files)
        assert len(errors) == 2
        all_errors = " ".join(errors)
        assert "missing_b" in all_errors
        assert "missing_c" in all_errors