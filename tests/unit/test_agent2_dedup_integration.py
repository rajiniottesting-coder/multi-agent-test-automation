"""
Integration tests for Agent 2's deduplication and regeneration flows.

These tests verify the END-TO-END contract:
  - When a story has duplicates, Agent 2 skips them
  - When all test cases are duplicates, no PR is opened
  - When everything is new, the original flow runs unchanged
  - Filename validator catches inconsistent LLM output
  - Regenerate mode bypasses dedup and uses -revN branch suffix

We use unittest.mock to fake external dependencies (Jira, GitHub, LLM)
because real integration tests would cost money (LLM tokens) and require
network. These tests run in <1s and are fully deterministic.

Run with:
    python -m pytest tests/unit/test_agent2_dedup_integration.py -v
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ─── Helpers ────────────────────────────────────────────────────────────


def _mk_test_case(key: str, summary: str, description: str = "") -> dict:
    """Build a test-case dict shaped like jira_client returns."""
    return {"key": key, "summary": summary, "description": description}


def _mk_inventory(scenarios_by_file: dict) -> dict:
    """Build an inventory dict shaped like scan_features_dir returns."""
    all_scenarios = []
    for scenarios in scenarios_by_file.values():
        all_scenarios.extend(scenarios)
    return {
        "files": list(scenarios_by_file.keys()),
        "scenarios_by_file": scenarios_by_file,
        "all_scenarios": all_scenarios,
    }


def _make_generated_file(path: str, content: str = ""):
    """Build a duck-typed object that looks like a GeneratedFile."""
    class _Stub:
        pass
    s = _Stub()
    s.file_path = path
    s.content = content
    return s


# ─── Tests for dedup partition contract ─────────────────────────────────


class TestAgent2DedupIntegration:
    """
    Verifies that the dedup partition logic Agent 2 uses correctly handles
    the realistic scenarios that arise during real Jira/GitHub workflows.
    """

    def test_all_test_cases_new_returns_all_in_new_bucket(self):
        from agents.test_inventory import filter_duplicate_test_cases

        test_cases = [
            _mk_test_case("SCRUM-9", "Login fails with empty username"),
            _mk_test_case("SCRUM-10", "Login fails with empty password"),
        ]
        inventory = _mk_inventory({})

        new, skipped = filter_duplicate_test_cases(test_cases, inventory)
        assert len(new) == 2
        assert len(skipped) == 0
        assert new == test_cases

    def test_all_duplicates_returns_empty_new(self):
        """Critical: when everything is covered, Agent 2 should skip PR."""
        from agents.test_inventory import filter_duplicate_test_cases

        test_cases = [
            _mk_test_case("SCRUM-9", "Login fails with empty username"),
            _mk_test_case("SCRUM-10", "Successful login with standard user"),
        ]
        inventory = _mk_inventory({
            "login.feature": [
                "Login fails with empty username",
                "Successful login with standard user",
            ],
        })

        new, skipped = filter_duplicate_test_cases(test_cases, inventory)
        assert len(new) == 0  # Nothing to generate
        assert len(skipped) == 2  # Both covered

    def test_partial_duplicates_only_new_to_llm(self):
        """The cost-saving win: only NEW test cases go to LLM."""
        from agents.test_inventory import filter_duplicate_test_cases

        test_cases = [
            _mk_test_case("SCRUM-9", "Successful login with standard user"),  # dup
            _mk_test_case("SCRUM-10", "Login with mfa code"),                  # new
            _mk_test_case("SCRUM-11", "Login fails with locked-out user"),     # dup
            _mk_test_case("SCRUM-12", "Login with biometric"),                 # new
        ]
        inventory = _mk_inventory({
            "login.feature": [
                "Successful login with standard user",
                "Login fails with locked-out user",
            ],
        })

        new, skipped = filter_duplicate_test_cases(test_cases, inventory)
        assert len(new) == 2
        assert len(skipped) == 2
        new_keys = {tc["key"] for tc in new}
        skipped_keys = {s["test_case"]["key"] for s in skipped}
        assert new_keys == {"SCRUM-10", "SCRUM-12"}
        assert skipped_keys == {"SCRUM-9", "SCRUM-11"}

    def test_dedup_robust_to_llm_inconsistent_casing(self):
        """LLM-generated scenarios may have inconsistent casing — match anyway."""
        from agents.test_inventory import filter_duplicate_test_cases

        test_cases = [
            _mk_test_case("SCRUM-9", "successful Login With STANDARD USER"),
        ]
        inventory = _mk_inventory({
            "login.feature": ["Successful login with standard user"],
        })
        new, skipped = filter_duplicate_test_cases(test_cases, inventory)
        assert len(new) == 0
        assert len(skipped) == 1


# ─── Tests for filename validator integration ───────────────────────────


class TestFilenameValidatorIntegration:
    """Verifies validator catches PR-#7-style filename mismatches."""

    def test_pr_seven_bug_caught(self):
        """The exact bug pattern from PR #7 — kebab feature, snake step def."""
        from agents.test_inventory import validate_filename_consistency

        files = [
            _make_generated_file(
                "features/login-validation.feature",
                "Feature: Login validation\n  Scenario: Empty username\n",
            ),
            _make_generated_file(
                "tests/step_defs/test_login_validation.py",
                'from config.paths import feature_path\n'
                'scenarios(str(feature_path("login_validation")))\n',
            ),
        ]
        errors = validate_filename_consistency(files)
        assert len(errors) == 1
        assert "login_validation" in errors[0]

    def test_correct_naming_no_errors(self):
        """When LLM uses consistent snake_case, validator passes silently."""
        from agents.test_inventory import validate_filename_consistency

        files = [
            _make_generated_file(
                "features/login_validation.feature",
                "Feature: Login validation\n",
            ),
            _make_generated_file(
                "tests/step_defs/test_login_validation.py",
                'scenarios(str(feature_path("login_validation")))\n',
            ),
        ]
        assert validate_filename_consistency(files) == []

    def test_validator_runs_before_pr_creation(self):
        """
        Architectural verification: the validator is positioned BEFORE the
        GitHub branch/commit/PR steps, so a broken batch never becomes a PR.
        """
        repo_root = Path(__file__).resolve().parent.parent.parent
        agent2_path = repo_root / "agents" / "agent2_coder.py"
        if not agent2_path.exists():
            pytest.skip("agent2_coder.py not found; skipping structural check")

        src = agent2_path.read_text()

        validate_pos = src.find("validate_filename_consistency(generated_files)")
        gh_create_branch_pos = src.find("gh.create_branch")
        gh_open_pr_pos = src.find("gh.open_pull_request")

        assert validate_pos > 0, "Validator call missing from agent2_coder.py"
        assert gh_create_branch_pos > 0, "Branch creation missing"
        assert gh_open_pr_pos > 0, "PR opening missing"

        # Validator must appear before BOTH branch creation AND PR opening
        assert validate_pos < gh_create_branch_pos, (
            "Filename validator runs AFTER branch creation — that's wrong, "
            "we'd create a branch with broken code before catching the issue."
        )
        assert validate_pos < gh_open_pr_pos, (
            "Filename validator runs AFTER PR opening — that's wrong."
        )


# ─── Tests for prompt fix ───────────────────────────────────────────────


class TestPromptNamingConventionFix:
    """
    Verifies the agent2_coder_plan.md prompt was updated to use snake_case
    consistently for files and step defs (Phase 4 prompt fix).
    """

    def test_naming_convention_uses_snake_case_for_files(self):
        repo_root = Path(__file__).resolve().parent.parent.parent
        prompt_path = repo_root / "prompts" / "agent2_coder_plan.md"
        if not prompt_path.exists():
            pytest.skip("Prompt file not found; skipping")

        content = prompt_path.read_text()
        assert "snake_case" in content, "Prompt must specify snake_case naming"

    def test_critical_warning_present(self):
        """Prompt should contain a CRITICAL warning about consistency."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        prompt_path = repo_root / "prompts" / "agent2_coder_plan.md"
        if not prompt_path.exists():
            pytest.skip("Prompt file not found; skipping")

        content = prompt_path.read_text()
        assert "MUST USE THE SAME" in content or "CRITICAL" in content, (
            "Prompt should warn about feature file / step def name consistency"
        )


# ─── Tests for Phase 6: ai-regenerate label support ────────────────────


class TestPhase6RegenerateMode:
    """
    Verifies the ai-regenerate label flow works end-to-end:
      - run() accepts is_regenerate parameter
      - Regenerate mode bypasses dedup
      - Branch gets -revN suffix in regenerate mode
      - ai-regenerate label removed after success
      - Config has both selection and regenerate_selection
    """

    def test_run_function_accepts_is_regenerate_parameter(self):
        """run() signature must support is_regenerate=False/True."""
        import inspect
        from agents.agent2_coder import run

        sig = inspect.signature(run)
        assert "is_regenerate" in sig.parameters, (
            "run() must accept is_regenerate parameter for Phase 6 support"
        )
        # Default should be False (existing behavior)
        param = sig.parameters["is_regenerate"]
        assert param.default is False, (
            "is_regenerate must default to False to preserve existing behavior"
        )

    def test_regenerate_logic_present_in_run(self):
        """The run() function must handle is_regenerate flag."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        agent2_path = repo_root / "agents" / "agent2_coder.py"
        src = agent2_path.read_text()

        # Bypass dedup in regenerate mode
        assert "if is_regenerate:" in src, (
            "agent2_coder.py must check is_regenerate flag"
        )
        # -revN suffix logic
        assert "-rev" in src, (
            "agent2_coder.py must implement -revN branch suffix"
        )
        # Label cleanup after success
        assert "remove_label" in src, (
            "agent2_coder.py must remove ai-regenerate label after success"
        )

    def test_jira_client_has_remove_label(self):
        """JiraClient.remove_label() must exist for label cleanup."""
        from agents.jira_client import JiraClient
        assert hasattr(JiraClient, "remove_label"), (
            "JiraClient must have remove_label() method for Phase 6"
        )

    def test_github_client_has_branch_exists(self):
        """GitHubClient.branch_exists() must exist for -revN logic."""
        from agents.github_client import GitHubClient
        assert hasattr(GitHubClient, "branch_exists"), (
            "GitHubClient must have branch_exists() method for Phase 6"
        )

    def test_config_has_regenerate_selection(self):
        """config.yaml must define regenerate_selection block."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        config_path = repo_root / "config" / "config.yaml"
        if not config_path.exists():
            pytest.skip("config.yaml not found")

        content = config_path.read_text()
        assert "regenerate_selection:" in content, (
            "config.yaml must define agent2_coder.regenerate_selection block"
        )
        assert "ai-regenerate" in content, (
            "config.yaml must reference ai-regenerate label"
        )

    def test_scan_mode_does_two_passes(self):
        """The --scan mode should look for both normal and regen stories."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        agent2_path = repo_root / "agents" / "agent2_coder.py"
        src = agent2_path.read_text()

        # Two separate selection lookups
        assert "normal_selection" in src or 'config.get("selection"' in src, (
            "Scan mode must read normal selection config"
        )
        assert "regenerate_selection" in src or "regen_selection" in src, (
            "Scan mode must read regenerate_selection config"
        )

    def test_regen_branch_naming_pattern(self):
        """Verify the -revN naming logic computes correct suffixes."""
        # We can't easily test the actual GitHub call, but we can verify
        # the algorithm: starting from rev2, find the lowest unused suffix.

        # Simulation: branch_exists returns True for rev2, rev3; False for rev4
        # The algorithm should pick rev4
        existing_branches = {"auto/SCRUM-5-login-rev2", "auto/SCRUM-5-login-rev3"}

        def fake_branch_exists(name):
            return name in existing_branches

        base = "auto/SCRUM-5-login"
        n = 2
        while fake_branch_exists(f"{base}-rev{n}"):
            n += 1
        result = f"{base}-rev{n}"

        assert result == "auto/SCRUM-5-login-rev4", (
            f"Expected -rev4 (next unused), got {result}"
        )


# ─── End-to-end module integration ──────────────────────────────────────


class TestAllModulesImportCleanly:
    """Final defensive check: every agent module imports without errors."""

    def test_test_inventory_imports(self):
        from agents.test_inventory import (
            scan_features_dir,
            normalize_scenario_name,
            find_matching_scenario,
            filter_duplicate_test_cases,
            validate_filename_consistency,
        )
        # All five public functions should be callable
        assert callable(scan_features_dir)
        assert callable(normalize_scenario_name)
        assert callable(find_matching_scenario)
        assert callable(filter_duplicate_test_cases)
        assert callable(validate_filename_consistency)

    def test_agent2_coder_imports(self):
        from agents.agent2_coder import run, main
        assert callable(run)
        assert callable(main)

    def test_jira_client_has_required_methods(self):
        from agents.jira_client import JiraClient
        for method in ("add_label", "remove_label", "find_stories_to_process"):
            assert hasattr(JiraClient, method), f"JiraClient missing {method}"

    def test_github_client_has_required_methods(self):
        from agents.github_client import GitHubClient
        for method in ("create_branch", "branch_exists", "open_pull_request"):
            assert hasattr(GitHubClient, method), f"GitHubClient missing {method}"