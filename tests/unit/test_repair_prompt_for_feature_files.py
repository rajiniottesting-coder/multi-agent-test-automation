"""A feature file is repaired from what it is: the repair is shown the file and
told to keep its markers, sees the right previous attempt, and the repair
prompt uses the same rule for every file type.
"""

from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[2]
FEATURE = """Feature: Help

  # JIRA: AB-2 (hash: 1234abcd) owner: AB-1
  @smoke
  Scenario: Reading help
    Given I am on the help page
    Then the help should be shown
"""


@pytest.mark.parametrize("path, content, shown", [
    ("features/help.feature", FEATURE, True),
    ("features/help.feature", "", False),
    ("features/help.feature", "garbage", False),
    ("tests/step_defs/test_help.py", "def broken(:\n", False),
])
def test_which_previous_attempt_a_repair_is_shown(path, content, shown):
    from agents.agent2_coder import _previous_attempt_worth_showing
    assert _previous_attempt_worth_showing(path, content) is shown


def test_a_feature_repair_is_shown_the_file_and_told_to_keep_its_markers():
    import agents.agent2_coder as a2
    from core.app_context import AppContext
    from core.schemas import CodePlan, FilePlan
    seen = {}

    class LLM:
        def invoke_text(self, system_prompt, user_prompt, **kw):
            seen["prompt"] = user_prompt
            return "```gherkin\n" + FEATURE + "```"

    fp = FilePlan(file_path="features/help.feature", file_type="feature", is_new_file=True,
                  purpose="p", related_test_cases=["AB-2"])
    plan = CodePlan(feature_name="f", branch_name="auto/AB-1-help", pr_title="t", pr_body="",
                    files_to_create=[fp])
    ctx = AppContext.load()
    a2.generate_file_content(LLM(), fp, plan, [{"key": "AB-2", "summary": "s", "description": "d"}],
                             ctx.load_reference_files(), "{}", ctx, previous_attempt=FEATURE,
                             validator_feedback=["Step coverage error in 'tests/step_defs/test_help.py': x"])
    prompt = seen["prompt"]
    assert "Your previous attempt" in prompt and "# JIRA: AB-2 (hash: 1234abcd)" in prompt
    assert "`# JIRA:` marker line" in prompt


def test_the_repair_prompt_uses_the_rule_for_every_file_type():
    src = (ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    assert "_previous_attempt_worth_showing(file_plan.file_path," in src
    assert "if previous_attempt and _looks_like_useful_python(previous_attempt):" not in src
