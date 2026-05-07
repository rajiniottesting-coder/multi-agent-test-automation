"""
Unit tests for the self-correcting step-coverage repair loop in
agents/agent2_coder.py.

The repair loop is designed to handle the failure mode where weaker LLMs
(particularly gemini-2.5-flash-lite) generate Gherkin step phrases that
don't have matching @given/@when/@then decorators in the paired step def
file. Instead of hard-failing, the framework now invokes the LLM a second
(and third) time with explicit validator feedback so it can fix only the
broken file.

These tests verify:
  - Error parsing / grouping by file
  - Repair loop terminates on success
  - Repair loop terminates on retry exhaustion
  - generate_file_content correctly handles repair-mode arguments
  - Targeted repair (only broken files re-generated, not the whole batch)

The tests use a fake LLM client and fake validator so they're hermetic
and run in milliseconds without any network calls or quota use.
"""
import pytest
from unittest.mock import patch, MagicMock

from agents.app_context import AppContext
from agents.agent2_coder import (
    _attempt_step_coverage_repair,
    _group_coverage_errors_by_step_def,
    generate_file_content,
)
from agents.schemas import CodePlan, FilePlan, GeneratedFile


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

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
def fake_plan():
    """A fake CodePlan matching the SCRUM-12 sort-feature scenario."""
    return CodePlan(
        feature_name="sort",
        branch_name="auto/TEST-1-sort",
        pr_title="Sort tests",
        pr_body="Adds sort tests",
        files_to_create=[
            FilePlan(
                file_path="features/sort.feature",
                file_type="feature",
                is_new_file=True,
                purpose="sort scenarios",
                related_test_cases=["TEST-1"],
            ),
            FilePlan(
                file_path="tests/step_defs/test_sort.py",
                file_type="step_definitions",
                is_new_file=True,
                purpose="sort step defs",
                related_test_cases=["TEST-1"],
            ),
        ],
    )


# ─────────────────────────────────────────────────────────────
# Error parsing
# ─────────────────────────────────────────────────────────────

class TestErrorGrouping:
    def test_groups_by_step_def_path(self):
        errors = [
            "Step coverage error in 'tests/step_defs/test_a.py': feature step `Then x` (from 'features/a.feature') has no matching @then() decorator. pytest-bdd would fail with StepDefinitionNotFoundError at test collection time.",
            "Step coverage error in 'tests/step_defs/test_a.py': feature step `When y` (from 'features/a.feature') has no matching @when() decorator. pytest-bdd would fail with StepDefinitionNotFoundError at test collection time.",
            "Step coverage error in 'tests/step_defs/test_b.py': feature step `Given z` (from 'features/b.feature') has no matching @given() decorator. pytest-bdd would fail with StepDefinitionNotFoundError at test collection time.",
        ]
        grouped = _group_coverage_errors_by_step_def(errors)
        assert set(grouped.keys()) == {"tests/step_defs/test_a.py", "tests/step_defs/test_b.py"}
        assert len(grouped["tests/step_defs/test_a.py"]) == 2
        assert len(grouped["tests/step_defs/test_b.py"]) == 1

    def test_unparseable_errors_dropped(self):
        """Errors that don't match the expected format don't crash the parser."""
        errors = [
            "Some unrelated error string",
            "Step coverage error in 'tests/step_defs/test_a.py': stuff",
        ]
        grouped = _group_coverage_errors_by_step_def(errors)
        assert len(grouped) == 1  # only the parseable one

    def test_empty_input(self):
        assert _group_coverage_errors_by_step_def([]) == {}


# ─────────────────────────────────────────────────────────────
# Repair loop control flow
# ─────────────────────────────────────────────────────────────

class TestRepairLoop:
    def test_no_errors_returns_immediately(self, ctx, fake_plan):
        """If validator finds nothing wrong, repair is a no-op."""
        files = [
            GeneratedFile(
                file_path="features/sort.feature",
                content="...",
                is_new_file=True,
                purpose="...",
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_sort.py",
                content="...",
                is_new_file=True,
                purpose="...",
            ),
        ]
        with patch("agents.agent2_coder.validate_step_definitions_complete", return_value=[]):
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, fake_plan, [], {}, "{}", ctx, max_retries=2
            )
        assert result is files
        # LLM should NOT have been called when there are no errors to fix
        llm.invoke_text.assert_not_called()

    def test_succeeds_after_one_retry(self, ctx, fake_plan):
        """Validator fails once, succeeds after one repair call."""
        # Realistic step-def content — must pass _looks_like_useful_python:
        # >500 chars, valid Python, has @given/@when/@then.
        prior_buggy_content = (
            "import pytest\n"
            "from pytest_bdd import scenarios, given, when, then, parsers\n"
            "from pages.login_page import LoginPage\n"
            "\n"
            "scenarios('features/sort.feature')\n"
            "\n"
            "@given('I am on the login page')\n"
            "def open_login(page):\n"
            "    pass\n"
            "\n"
            "@when('I do something')\n"
            "def do_something(page):\n"
            "    pass\n"
            "# Note: this file is missing the @then for 'Then missing' from the feature\n"
            "# This is intentional for the test — the validator should flag it.\n"
            "\n"
        ) * 3  # repeat to reach > 500 chars

        repaired_content = prior_buggy_content + (
            "\n@then('missing')\n"
            "def now_present(page):\n"
            "    assert True\n"
        )

        files = [
            GeneratedFile(
                file_path="features/sort.feature",
                content="Feature: x\n  Scenario: y\n    Then missing\n",
                is_new_file=True,
                purpose="...",
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_sort.py",
                content=prior_buggy_content,
                is_new_file=True,
                purpose="...",
            ),
        ]
        validator_calls = []
        def fake_validator(*_args, **_kwargs):
            validator_calls.append(1)
            if len(validator_calls) == 1:
                return [
                    "Step coverage error in 'tests/step_defs/test_sort.py': "
                    "feature step `Then missing` (from 'features/sort.feature') "
                    "has no matching @then() decorator. "
                    "pytest-bdd would fail with StepDefinitionNotFoundError at test collection time."
                ]
            return []  # second call: all clear

        with patch("agents.agent2_coder.validate_step_definitions_complete", side_effect=fake_validator), \
             patch("agents.agent2_coder.generate_file_content", return_value=repaired_content) as mock_gen:
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, fake_plan, [], {}, "{}", ctx, max_retries=2
            )

        # generate_file_content called exactly once (the broken file)
        assert mock_gen.call_count == 1
        # Validator called twice: initial + post-repair check
        assert len(validator_calls) == 2
        # The broken file's content was replaced
        sort_step_def = next(f for f in result if f.file_path == "tests/step_defs/test_sort.py")
        assert sort_step_def.content == repaired_content

    def test_exhausts_retries_when_repair_fails_with_real_content(self, ctx, fake_plan):
        """If the LLM produces realistic-looking content but it's still wrong,
        retries continue up to max_retries."""
        # Realistic content (>500 chars, valid Python) on every retry
        realistic_content = (
            "import pytest\n"
            "from pytest_bdd import scenarios, given, when, then\n"
            "from pages.login_page import LoginPage\n"
            "\n"
            "scenarios('features/sort.feature')\n"
            "\n"
            "@given('I am here')\n"
            "def here(page):\n"
            "    pass\n"
            "# Real-looking but the validator still flags missing decorators.\n"
            "# This simulates the LLM producing valid Python but missing\n"
            "# coverage of every Gherkin step.\n"
        ) * 4

        files = [
            GeneratedFile(
                file_path="features/sort.feature",
                content="Feature: x",
                is_new_file=True,
                purpose="...",
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_sort.py",
                content=realistic_content,
                is_new_file=True,
                purpose="...",
            ),
        ]
        persistent_error = [
            "Step coverage error in 'tests/step_defs/test_sort.py': "
            "feature step `Then x` (from 'features/sort.feature') has no matching @then() decorator. "
            "pytest-bdd would fail with StepDefinitionNotFoundError at test collection time."
        ]
        with patch("agents.agent2_coder.validate_step_definitions_complete", return_value=persistent_error), \
             patch("agents.agent2_coder.generate_file_content", return_value=realistic_content) as mock_gen:
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, fake_plan, [], {}, "{}", ctx, max_retries=2
            )

        # generate_file_content called exactly max_retries times
        assert mock_gen.call_count == 2
        # Returns generated_files for final validator to raise on
        assert result is not None

    def test_aborts_early_on_degraded_output(self, ctx, fake_plan):
        """NEW: If repair produces tiny/broken output, abort before retry 2."""
        realistic_prior_content = (
            "import pytest\n"
            "from pytest_bdd import scenarios, given, when, then\n"
            "from pages.login_page import LoginPage\n"
            "scenarios('features/sort.feature')\n"
            "@given('something')\n"
            "def s(p): pass\n"
        ) * 5  # > 500 chars, parses fine

        files = [
            GeneratedFile(
                file_path="features/sort.feature",
                content="Feature: x",
                is_new_file=True,
                purpose="...",
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_sort.py",
                content=realistic_prior_content,
                is_new_file=True,
                purpose="...",
            ),
        ]
        persistent_error = [
            "Step coverage error in 'tests/step_defs/test_sort.py': "
            "feature step `Then x` (from 'features/sort.feature') has no matching @then() decorator. "
            "pytest-bdd would fail with StepDefinitionNotFoundError at test collection time."
        ]
        # LLM returns truncated stub on first repair — should trigger abort
        truncated_garbage = "Here's the corrected file:\n```python\nimport"
        with patch("agents.agent2_coder.validate_step_definitions_complete", return_value=persistent_error), \
             patch("agents.agent2_coder.generate_file_content", return_value=truncated_garbage) as mock_gen:
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, fake_plan, [], {}, "{}", ctx, max_retries=2
            )

        # Repair aborts after first degraded output — only 1 call, not 2
        assert mock_gen.call_count == 1, (
            f"Expected early abort after degraded output, but LLM was called "
            f"{mock_gen.call_count} times. Degradation detection isn't working."
        )
        # Original prior content should be preserved
        sort_step_def = next(f for f in result if f.file_path == "tests/step_defs/test_sort.py")
        assert sort_step_def.content == realistic_prior_content

    def test_only_broken_files_regenerated(self, ctx, fake_plan):
        """Repair should not re-generate files that aren't flagged."""
        files = [
            GeneratedFile(
                file_path="features/sort.feature",
                content="Feature: x",
                is_new_file=True,
                purpose="...",
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_sort.py",
                content="# broken",
                is_new_file=True,
                purpose="...",
            ),
        ]
        validator_calls = [0]
        def fake_validator(*_args, **_kwargs):
            validator_calls[0] += 1
            if validator_calls[0] == 1:
                return [
                    "Step coverage error in 'tests/step_defs/test_sort.py': "
                    "feature step `Then x` (from 'features/sort.feature') has no matching @then() decorator. "
                    "pytest-bdd would fail with StepDefinitionNotFoundError at test collection time."
                ]
            return []

        with patch("agents.agent2_coder.validate_step_definitions_complete", side_effect=fake_validator), \
             patch("agents.agent2_coder.generate_file_content", return_value="# fixed") as mock_gen:
            llm = MagicMock()
            _attempt_step_coverage_repair(
                files, llm, fake_plan, [], {}, "{}", ctx, max_retries=2
            )

        # Only the step def was regenerated, not the feature file
        assert mock_gen.call_count == 1
        called_with_path = mock_gen.call_args[0][1].file_path
        assert called_with_path == "tests/step_defs/test_sort.py"

    def test_validator_feedback_passed_to_generation(self, ctx, fake_plan):
        """The repair call must pass the actual validator errors as feedback."""
        files = [
            GeneratedFile(
                file_path="tests/step_defs/test_sort.py",
                content="# broken",
                is_new_file=True,
                purpose="...",
            ),
        ]
        # We need a feature file in the plan too for proper grouping
        files.insert(0, GeneratedFile(
            file_path="features/sort.feature",
            content="...",
            is_new_file=True,
            purpose="...",
        ))

        target_error = (
            "Step coverage error in 'tests/step_defs/test_sort.py': "
            "feature step `Then sorted ascending` (from 'features/sort.feature') "
            "has no matching @then() decorator. "
            "pytest-bdd would fail with StepDefinitionNotFoundError at test collection time."
        )
        validator_calls = [0]
        def fake_validator(*_args, **_kwargs):
            validator_calls[0] += 1
            if validator_calls[0] == 1:
                return [target_error]
            return []

        with patch("agents.agent2_coder.validate_step_definitions_complete", side_effect=fake_validator), \
             patch("agents.agent2_coder.generate_file_content", return_value="# fixed") as mock_gen:
            llm = MagicMock()
            _attempt_step_coverage_repair(
                files, llm, fake_plan, [], {}, "{}", ctx, max_retries=2
            )

        # The validator_feedback kwarg must contain the target error
        kwargs = mock_gen.call_args.kwargs
        assert "validator_feedback" in kwargs
        assert target_error in kwargs["validator_feedback"]
        assert "previous_attempt" in kwargs
        assert kwargs["previous_attempt"] == "# broken"


# ─────────────────────────────────────────────────────────────
# generate_file_content with repair-mode arguments
# ─────────────────────────────────────────────────────────────

class TestGenerateFileContentRepairMode:
    def test_normal_mode_no_feedback_block(self, ctx, fake_plan, tmp_path):
        """Without validator_feedback, the prompt has an empty feedback block."""
        file_plan = fake_plan.files_to_create[1]  # the step def file
        captured_prompt = []

        class FakeLLM:
            def invoke_text(self, system_prompt, user_prompt):
                captured_prompt.append(user_prompt)
                return "```python\n# step def\n```"

        result = generate_file_content(
            FakeLLM(),
            file_plan,
            fake_plan,
            test_cases=[{"key": "TEST-1", "summary": "x", "description": "y"}],
            references={"feature": "", "step_def": "", "page_object": ""},
            page_inventory="{}",
            ctx=ctx,
        )
        assert result == "# step def\n"
        # Feedback block should not have content when validator_feedback=None
        assert "Validator Feedback" not in captured_prompt[0]

    def test_repair_mode_includes_feedback(self, ctx, fake_plan, tmp_path):
        """With validator_feedback, the prompt explicitly lists the issues."""
        file_plan = fake_plan.files_to_create[1]
        captured_prompt = []

        class FakeLLM:
            def invoke_text(self, system_prompt, user_prompt):
                captured_prompt.append(user_prompt)
                return "```python\n# corrected step def\n```"

        feedback = [
            "Step coverage error: feature step `Then x` has no matching @then().",
            "Step coverage error: feature step `When y` has no matching @when().",
        ]
        result = generate_file_content(
            FakeLLM(),
            file_plan,
            fake_plan,
            test_cases=[{"key": "TEST-1", "summary": "x", "description": "y"}],
            references={"feature": "", "step_def": "", "page_object": ""},
            page_inventory="{}",
            ctx=ctx,
            validator_feedback=feedback,
            previous_attempt="# original buggy",
        )
        assert result == "# corrected step def\n"
        prompt = captured_prompt[0]
        assert "Fix these validation issues" in prompt
        # Step phrases get extracted from the verbose error strings
        assert "Then x" in prompt
        assert "When y" in prompt
        # Previous attempt is NOT shown when it's not parseable Python
        # (the test passes "# original buggy" which is just a comment, not real code)


# ─────────────────────────────────────────────────────────────
# Hotfix v4 helpers — feedback summarization + degraded output detection
# ─────────────────────────────────────────────────────────────

from agents.agent2_coder import (
    _summarize_validator_feedback,
    _looks_like_useful_python,
    _is_degraded_regeneration,
)


class TestFeedbackSummarization:
    """Compact validator errors so the LLM doesn't drown in repetition."""

    def test_few_errors_listed_verbatim(self):
        errors = [
            "Step coverage error in 'tests/x.py': feature step `Then a` (from 'features/x.feature') has no matching @then() decorator. ...",
            "Step coverage error in 'tests/x.py': feature step `When b` (from 'features/x.feature') has no matching @when() decorator. ...",
        ]
        summary = _summarize_validator_feedback(errors)
        assert "Then a" in summary
        assert "When b" in summary
        # Small enough to be readable
        assert len(summary) < 300

    def test_many_errors_summarized(self):
        """22 errors get truncated with a count of remaining."""
        errors = [
            f"Step coverage error in 'tests/x.py': feature step `Step {i}` (from 'features/x.feature') has no matching @when() decorator. ..."
            for i in range(22)
        ]
        summary = _summarize_validator_feedback(errors)
        # First 8 shown verbatim
        assert "Step 0" in summary
        assert "Step 7" in summary
        # Remainder summarized
        assert "and 14 more" in summary
        # Compact relative to original
        verbatim_size = sum(len(e) for e in errors)
        assert len(summary) < verbatim_size * 0.2  # > 80% reduction

    def test_empty_list(self):
        assert _summarize_validator_feedback([]) == ""

    def test_non_step_coverage_errors(self):
        """Import errors don't have `feature step` pattern — should still extract first 150 chars."""
        errors = [
            "Import resolution error in 'tests/x.py': line 7 has `import pages.foo` but module does not exist on disk."
        ]
        summary = _summarize_validator_feedback(errors)
        assert "pages.foo" in summary or "module does not exist" in summary


class TestDegradedOutputDetection:
    """Recognize when the LLM has given up producing useful content."""

    def test_real_code_accepted(self):
        good = (
            "import pytest\nfrom pytest_bdd import given\n"
            "@given('x')\ndef x(p): pass\n"
        ) * 10
        assert _looks_like_useful_python(good) is True
        assert _is_degraded_regeneration(good, good) is False

    def test_tiny_output_degraded(self):
        """Output under 500 chars is treated as a stub."""
        assert _looks_like_useful_python("# tiny") is False
        assert _is_degraded_regeneration("# tiny", "x" * 1000) is True

    def test_empty_output_degraded(self):
        assert _is_degraded_regeneration("", "x" * 1000) is True

    def test_syntax_error_degraded(self):
        """Truncated mid-statement output fails to parse."""
        truncated = "Here's the file:\n```python\nimport pytest\nfrom pytest_bdd "  # cuts off
        assert _looks_like_useful_python(truncated) is False
        assert _is_degraded_regeneration(truncated, "x" * 1000) is True

    def test_dramatic_size_reduction_degraded(self):
        """If new content is < 30% of prior real code, it's a degradation signal."""
        prior = (
            "import pytest\nfrom pytest_bdd import given\n"
            "@given('x')\ndef x(p): pass\n"
        ) * 20  # ~1500 chars
        # New attempt is ~600 chars but valid Python
        new = (
            "import pytest\n"
            "from pytest_bdd import given\n"
            "@given('y')\n"
            "def y(p): pass\n"
        ) * 10  # ~700 chars - greater than 30% threshold, so NOT degraded
        # That should NOT be flagged
        assert _is_degraded_regeneration(new, prior) is False

        # But a 20-line response when prior was 200 lines — degraded
        very_small = "import pytest\n@given('x')\ndef x(p): pass\n" * 3
        assert len(very_small) < 0.3 * len(prior)
        assert _is_degraded_regeneration(very_small, prior) is True

    def test_handles_no_prior_content(self):
        """If there's no useful prior content, only check absolute thresholds."""
        # Reasonable output (>500 chars), no prior to compare to
        good = (
            "import pytest\n"
            "@given('x')\n"
            "def x(p): pass\n"
        ) * 20  # > 500 chars
        assert _is_degraded_regeneration(good, "") is False

        # Tiny output is still degraded regardless of prior
        assert _is_degraded_regeneration("# stub", "") is True