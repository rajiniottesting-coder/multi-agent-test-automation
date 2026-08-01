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
from core.app_context import AppContext
from core.schemas import CodePlan, FilePlan, GeneratedFile


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
        "from pages.some_page import SomePage\n"
        "from pages.inventory_page import InventoryPage\n"
        "\n"
        "scenarios('features/logout.feature')\n"
        "\n"
        "@pytest.fixture\n"
        "def some_page(page):\n"
        "    return SomePage(page)\n"
        "\n"
        "@pytest.fixture\n"
        "def inventory_page(page):\n"
        "    return InventoryPage(page)\n"
        "\n"
        "@given('I am on the login page')\n"
        "def open_login(some_page, base_url):\n"
        "    some_page.open(base_url)\n"
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
            "@then('I see login page')\ndef verify(some_page):\n    assert True\n"
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
    def test_an_unchanged_error_set_stops_the_loop(self, ctx, plan):
        """CONTRACT CHANGED 31 Jul 2026. This used to assert the loop spent
        every retry on a persistent error. A real run did exactly that: four
        attempts, the same unused-step error verbatim each time, near-identical
        output, nothing fixed, $1.74 spent.

        An attempt that leaves the error set byte-identical is not converging,
        so the loop now stops and lets the final gate report it. The old
        behaviour is still covered by
        test_changing_errors_still_use_every_retry below - progress, however
        partial, always earns another attempt.
        """
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

        # One repair attempt, then the identical error set aborts the loop.
        assert mock_gen.call_count == 1

    def test_changing_errors_still_use_every_retry(self, ctx, plan):
        """Partial progress must never be mistaken for a stuck loop: as long
        as each attempt changes something, the model keeps its full budget."""
        files = [
            GeneratedFile(
                file_path="tests/step_defs/test_logout.py",
                content=realistic_step_def(),
                is_new_file=True, purpose="...",
            ),
        ]
        counter = {"n": 0}

        def _always_different(*_a, **_k):
            counter["n"] += 1
            return [f"Step coverage error in 'tests/step_defs/test_logout.py': "
                    f"round {counter['n']}"]

        with patch("agents.agent2_coder._collect_repairable_errors",
                   side_effect=_always_different), \
             patch("agents.agent2_coder.generate_file_content",
                   return_value=realistic_step_def()) as mock_gen:
            llm = MagicMock()
            _attempt_step_coverage_repair(
                files, llm, plan, [], {}, "{}", ctx, max_retries=3
            )

        assert mock_gen.call_count == 3, "a different error each round is progress"

    def test_an_empty_error_set_is_success_not_stagnation(self, ctx, plan):
        """Two clean rounds in a row must return happily, not trip the abort."""
        files = [
            GeneratedFile(
                file_path="tests/step_defs/test_logout.py",
                content=realistic_step_def(),
                is_new_file=True, purpose="...",
            ),
        ]
        with patch("agents.agent2_coder._collect_repairable_errors", return_value=[]), \
             patch("agents.agent2_coder.generate_file_content") as mock_gen:
            llm = MagicMock()
            out = _attempt_step_coverage_repair(
                files, llm, plan, [], {}, "{}", ctx, max_retries=4
            )
        assert mock_gen.call_count == 0
        assert out == files


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


# ---------------------------------------------------------------------------
# Empty-output guard (Day 8 fix for Pro thinking-token exhaustion)
# ---------------------------------------------------------------------------
class TestEmptyOutputGuard:
    """Pro models can return HTTP 200 with near-zero content when their
    thinking budget is exhausted before producing visible output. The guard
    in generate_file_content() must reject that, not silently commit empty
    files like PR #16 did."""

    REFS = {"feature": "Feature: ref\n", "step_def": "# ref\n", "page_object": "# ref\n"}

    def test_one_char_output_rejected(self, ctx, plan):
        """The exact PR #16 failure mode: 1-char output must raise, not return."""
        from agents.agent2_coder import generate_file_content

        file_plan = plan.files_to_create[0]
        llm = MagicMock()
        llm.invoke_text.return_value = "\n"  # 1 char, like the real failure

        with pytest.raises(ValueError, match="suspiciously short"):
            generate_file_content(
                llm=llm, file_plan=file_plan, plan=plan,
                test_cases=[], references=self.REFS,
                page_inventory="", ctx=ctx,
            )

    def test_empty_string_output_rejected(self, ctx, plan):
        """Edge case: completely empty response."""
        from agents.agent2_coder import generate_file_content

        file_plan = plan.files_to_create[0]
        llm = MagicMock()
        llm.invoke_text.return_value = ""

        with pytest.raises(ValueError, match="suspiciously short"):
            generate_file_content(
                llm=llm, file_plan=file_plan, plan=plan,
                test_cases=[], references=self.REFS,
                page_inventory="", ctx=ctx,
            )

    def test_real_content_passes(self, ctx, plan):
        """Negative control: a real-sized file must NOT trigger the guard."""
        from agents.agent2_coder import generate_file_content

        file_plan = plan.files_to_create[0]
        llm = MagicMock()
        llm.invoke_text.return_value = (
            "Feature: Logout\n"
            "  Scenario: User logs out\n"
            "    Given I am on the inventory page\n"
            "    When I click the logout link\n"
            "    Then I should be on the login page\n"
        )
        result = generate_file_content(
            llm=llm, file_plan=file_plan, plan=plan,
            test_cases=[], references=self.REFS,
            page_inventory="", ctx=ctx,
        )
        assert "Logout" in result


# ─────────────────────────────────────────────────────────────────────────
# SCRUM-103, 31 Jul 2026 — the repair loop never saw the real error
#
# A run spent all four attempts repairing a step-def file for an unused step
# definition, produced near-identical output each time, and died on a
# page-object selector error it had never been shown. Two causes: the
# selector validator was not in the repair set at all, and the error router's
# regex could not parse `... error in '<path>' line 125:` even if it had been.
# ─────────────────────────────────────────────────────────────────────────
from agents.agent2_coder import (
    _collect_repairable_errors,
    _group_validator_errors_by_file,
)
from core.schemas import GeneratedFile


def _gf(path, content):
    return GeneratedFile(file_path=path, content=content,
                         is_new_file=True, purpose="t")


_OFFENDING_PAGE = (
    'from pages.base_page import BasePage\n\n\n'
    'class AdminAddUserPage(BasePage):\n'
    '    INVENTORY_PAGE = "admin_add_user"\n\n'
    '    def pick(self) -> None:\n'
    '        self.wait_visible(self.sel("autocomplete_option"))\n'
)


class TestSelectorErrorsAreRepairable:

    def test_a_line_numbered_error_routes_to_its_file(self):
        """The exact string from the failed run. The old regex required a
        colon straight after the closing quote, so this matched nothing, the
        error was dropped, and no repair was ever attempted."""
        err = ("Selector inventory error in 'pages/admin_add_user_page.py' "
               "line 125: AdminAddUserPage.wait_visible() is called with "
               "self.sel('autocomplete_option') ...")
        assert _group_validator_errors_by_file([err]) == {
            "pages/admin_add_user_page.py": [err]}

    def test_errors_without_a_line_number_still_route(self):
        err = "Selector inventory error in 'pages/y_page.py': class Y ..."
        assert list(_group_validator_errors_by_file([err])) == ["pages/y_page.py"]

    @pytest.mark.parametrize("err", [
        "Step coverage error in 'tests/step_defs/test_x.py': missing @when",
        "Import resolution error in 'tests/step_defs/test_x.py': bad import",
        "Unused step-definition error in 'tests/step_defs/test_x.py': unused",
        "Method resolution error in 'tests/step_defs/test_x.py': no such method",
    ])
    def test_every_other_error_shape_is_untouched(self, err):
        """The regex change must not narrow what already worked."""
        assert list(_group_validator_errors_by_file([err])) == [
            "tests/step_defs/test_x.py"]

    def test_unparseable_errors_are_still_skipped(self):
        assert _group_validator_errors_by_file(["something with no file"]) == {}

    def test_selector_errors_reach_the_repair_loop(self):
        """Previously enforced only by the final gate, so the model got four
        attempts at the wrong file and none at this one.

        Uses a LITERAL selector, which the validator rejects from the source
        text alone. Inventory-dependent checks degrade to a no-op when no
        inventory is readable - correct behaviour, but it would make this test
        depend on which app is configured, and on that app having been crawled.
        """
        page = (
            'from pages.base_page import BasePage\n\n\n'
            'class GhostPage(BasePage):\n'
            '    ROW_ICON = ".result-row .trash-icon"\n\n'
            '    def go(self) -> None:\n'
            '        self.click(self.ROW_ICON)\n'
        )
        errors = _collect_repairable_errors([_gf("pages/ghost_page.py", page)])
        selector = [e for e in errors if "Selector inventory error" in e]
        assert len(selector) == 1
        assert list(_group_validator_errors_by_file(selector)) == [
            "pages/ghost_page.py"]

    def test_a_clean_page_object_adds_no_repair_work(self):
        """A page object that declares no INVENTORY_PAGE and resolves no
        selectors is not a selector problem, whatever the configured app."""
        clean = (
            'from pages.base_page import BasePage\n\n\n'
            'class QuietPage(BasePage):\n'
            '    """A helper page object that resolves nothing."""\n\n'
            '    def describe(self) -> str:\n'
            '        return "nothing to see here"\n'
        )
        errors = _collect_repairable_errors([_gf("pages/quiet_page.py", clean)])
        assert [e for e in errors if "Selector inventory error" in e] == []