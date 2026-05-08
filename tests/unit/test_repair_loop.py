"""Repair-loop tests for the self-correcting validator retry mechanism.

When a validator finds a fixable issue (missing decorator, hallucinated
import, method name mismatch), the repair loop regenerates ONLY the
broken file with explicit feedback so the LLM can self-correct. This
file tests the loop's three guarantees:

    1. SUCCESS PATH:    Errors → repair call → no errors → return.
    2. EXHAUSTION PATH: Errors persist after max_retries → return last
                        attempt and let final validator raise.
    3. DEGRADED OUTPUT: If a repair attempt produces clearly worse
                        content (truncated, syntax-broken, much smaller),
                        keep the prior attempt and abort early.

These behaviors are the v2 + v4 hotfixes that prevented broken code
from reaching PRs in the past. The tests are hermetic — no LLM calls,
no network, no quota use.
"""
from unittest.mock import MagicMock, patch

import pytest

from agents.agent2_coder import _attempt_step_coverage_repair
from agents.app_context import AppContext
from agents.schemas import CodePlan, FilePlan, GeneratedFile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def ctx():
    return AppContext(
        name="TestApp",
        base_url="https://example.com",
        inventory_file="app_inventory/test.json",
        reference_feature="features/ref.feature",
        reference_step_def="tests/step_defs/test_ref.py",
        reference_page_object="pages/ref_page.py",
        reserved_paths=("features/ref.feature",),
        extendable_paths=("pages/extendable_page.py",),
    )


@pytest.fixture
def plan():
    """Two-file plan: one feature + one step def."""
    return CodePlan(
        feature_name="logout",
        branch_name="auto/TEST-1-logout",
        pr_title="Logout tests",
        pr_body="Adds logout tests",
        files_to_create=[
            FilePlan(
                file_path="features/logout.feature",
                file_type="feature",
                is_new_file=True,
                purpose="logout scenarios",
                related_test_cases=["TEST-1"],
            ),
            FilePlan(
                file_path="tests/step_defs/test_logout.py",
                file_type="step_definitions",
                is_new_file=True,
                purpose="logout step defs",
                related_test_cases=["TEST-1"],
            ),
        ],
    )


# Realistic step-def content — passes the >500 char + valid-Python heuristic
# that _is_degraded_regeneration uses to detect garbage output.
def realistic_step_def(extra_decorator: str = "") -> str:
    base = (
        "import pytest\n"
        "from pytest_bdd import scenarios, given, when, then, parsers\n"
        "from pages.login_page import LoginPage\n"
        "from pages.inventory_page import InventoryPage\n"
        "\n"
        "scenarios('features/logout.feature')\n"
        "\n"
        "@pytest.fixture\n"
        "def login_page(page):\n"
        "    return LoginPage(page)\n"
        "\n"
        "@pytest.fixture\n"
        "def inventory_page(page):\n"
        "    return InventoryPage(page)\n"
        "\n"
        "@given('I am on the login page')\n"
        "def open_login(login_page, base_url):\n"
        "    login_page.open(base_url)\n"
        "\n"
        "@when('I click logout')\n"
        "def click_logout(inventory_page):\n"
        "    inventory_page.click_logout()\n"
        "\n"
    )
    return base + extra_decorator


# ---------------------------------------------------------------------------
# 1. SUCCESS PATH
# ---------------------------------------------------------------------------
class TestRepairSucceedsAfterRetry:
    def test_no_errors_no_repair_call(self, ctx, plan):
        """Empty validator means immediate return with zero LLM calls."""
        files = [
            GeneratedFile(
                file_path="features/logout.feature", content="...",
                is_new_file=True, purpose="..."
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_logout.py", content="...",
                is_new_file=True, purpose="..."
            ),
        ]
        with patch("agents.agent2_coder._collect_repairable_errors", return_value=[]):
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, plan, [], {}, "{}", ctx, max_retries=2
            )
        assert result is files
        llm.invoke_text.assert_not_called()

    def test_first_repair_attempt_succeeds(self, ctx, plan):
        """One error on first check → one repair call → second check passes."""
        broken_content = realistic_step_def()
        repaired_content = realistic_step_def(
            "@then('I see login page')\ndef verify(login_page):\n    assert True\n"
        )

        files = [
            GeneratedFile(
                file_path="features/logout.feature",
                content="Feature: x\n  Scenario: y\n    Then I see login page\n",
                is_new_file=True, purpose="..."
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_logout.py",
                content=broken_content,
                is_new_file=True, purpose="..."
            ),
        ]

        # First validator call returns errors; subsequent calls clean.
        validator_calls = [0]
        def fake_collect(_files):
            validator_calls[0] += 1
            if validator_calls[0] == 1:
                return [
                    "Step coverage error in 'tests/step_defs/test_logout.py': "
                    "feature step `Then I see login page` (from 'features/logout.feature') "
                    "has no matching @then() decorator. "
                    "pytest-bdd would fail with StepDefinitionNotFoundError at test collection time."
                ]
            return []

        with patch("agents.agent2_coder._collect_repairable_errors", side_effect=fake_collect), \
             patch("agents.agent2_coder.generate_file_content", return_value=repaired_content) as mock_gen:
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, plan, [], {}, "{}", ctx, max_retries=2
            )

        assert mock_gen.call_count == 1
        assert validator_calls[0] == 2  # initial + post-repair re-check
        # Broken file replaced with repaired content
        repaired_file = next(f for f in result if f.file_path == "tests/step_defs/test_logout.py")
        assert repaired_file.content == repaired_content


# ---------------------------------------------------------------------------
# 2. EXHAUSTION PATH
# ---------------------------------------------------------------------------
class TestRepairExhaustsRetries:
    def test_persistent_errors_exhaust_retries(self, ctx, plan):
        """If errors persist on every retry, return last attempt — final
        validator will then raise. Cap at max_retries calls."""
        files = [
            GeneratedFile(
                file_path="features/logout.feature",
                content="Feature: x\n  Scenario: y\n    Then missing\n",
                is_new_file=True, purpose="..."
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_logout.py",
                content=realistic_step_def(),
                is_new_file=True, purpose="..."
            ),
        ]

        persistent_error = [
            "Step coverage error in 'tests/step_defs/test_logout.py': "
            "feature step `Then missing` (from 'features/logout.feature') "
            "has no matching @then() decorator. "
            "pytest-bdd would fail with StepDefinitionNotFoundError at test collection time."
        ]

        with patch("agents.agent2_coder._collect_repairable_errors", return_value=persistent_error), \
             patch("agents.agent2_coder.generate_file_content", return_value=realistic_step_def()) as mock_gen:
            llm = MagicMock()
            _attempt_step_coverage_repair(
                files, llm, plan, [], {}, "{}", ctx, max_retries=2
            )

        # Repair attempted exactly max_retries times before giving up
        assert mock_gen.call_count == 2


# ---------------------------------------------------------------------------
# 3. DEGRADED OUTPUT (Hotfix v4)
# ---------------------------------------------------------------------------
class TestDegradedOutputDetection:
    def test_tiny_repair_output_aborts_early(self, ctx, plan):
        """If the LLM returns a stub or near-empty file, keep the prior
        (better) attempt and abort the loop."""
        prior_good = realistic_step_def()
        tiny_garbage = "import pytest\n# TODO\n"  # <500 chars, no real code

        files = [
            GeneratedFile(
                file_path="features/logout.feature",
                content="Feature: x\n  Scenario: y\n    Then missing\n",
                is_new_file=True, purpose="..."
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_logout.py",
                content=prior_good,
                is_new_file=True, purpose="..."
            ),
        ]

        with patch("agents.agent2_coder._collect_repairable_errors",
                   return_value=["Step coverage error in 'tests/step_defs/test_logout.py': "
                                 "feature step `Then missing` has no matching @then() decorator."]), \
             patch("agents.agent2_coder.generate_file_content", return_value=tiny_garbage) as mock_gen:
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, plan, [], {}, "{}", ctx, max_retries=2
            )

        # Repair was tried once, detected as degraded, prior content preserved
        assert mock_gen.call_count == 1
        kept = next(f for f in result if f.file_path == "tests/step_defs/test_logout.py")
        assert kept.content == prior_good, "Should have kept the prior good content"

    def test_syntax_error_output_aborts_early(self, ctx, plan):
        """If the LLM returns code that doesn't even parse, keep prior attempt."""
        prior_good = realistic_step_def()
        broken_python = "def foo(:\n    return 1\nclass Bar(:\n    pass\n" * 50  # > 500 chars but unparseable

        files = [
            GeneratedFile(
                file_path="features/logout.feature",
                content="Feature: x\n  Scenario: y\n    Then x\n",
                is_new_file=True, purpose="..."
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_logout.py",
                content=prior_good,
                is_new_file=True, purpose="..."
            ),
        ]

        with patch("agents.agent2_coder._collect_repairable_errors",
                   return_value=["Step coverage error in 'tests/step_defs/test_logout.py': "
                                 "feature step `Then x` has no matching @then() decorator."]), \
             patch("agents.agent2_coder.generate_file_content", return_value=broken_python):
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, plan, [], {}, "{}", ctx, max_retries=2
            )

        kept = next(f for f in result if f.file_path == "tests/step_defs/test_logout.py")
        assert kept.content == prior_good