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
        files = [
            GeneratedFile(
                file_path="features/sort.feature",
                content="Feature: x\n  Scenario: y\n    Then missing\n",
                is_new_file=True,
                purpose="...",
            ),
            GeneratedFile(
                file_path="tests/step_defs/test_sort.py",
                content="# original buggy step def with missing decorator\n",
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
             patch("agents.agent2_coder.generate_file_content", return_value="# corrected step def\n") as mock_gen:
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
        assert sort_step_def.content == "# corrected step def\n"

    def test_exhausts_retries_when_repair_fails(self, ctx, fake_plan):
        """If the LLM keeps producing broken output, give up after max_retries."""
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
        # Validator always returns errors — LLM never converges
        persistent_error = [
            "Step coverage error in 'tests/step_defs/test_sort.py': "
            "feature step `Then x` (from 'features/sort.feature') has no matching @then() decorator. "
            "pytest-bdd would fail with StepDefinitionNotFoundError at test collection time."
        ]
        with patch("agents.agent2_coder.validate_step_definitions_complete", return_value=persistent_error), \
             patch("agents.agent2_coder.generate_file_content", return_value="# still broken\n") as mock_gen:
            llm = MagicMock()
            result = _attempt_step_coverage_repair(
                files, llm, fake_plan, [], {}, "{}", ctx, max_retries=2
            )

        # generate_file_content called exactly max_retries times for the broken file
        assert mock_gen.call_count == 2  # one per retry
        # Result is returned (will be caught by final validator, not by repair)
        assert result is not None

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
        assert "Validator Feedback" in prompt
        assert "Then x" in prompt
        assert "When y" in prompt
        assert "# original buggy" in prompt  # previous attempt shown