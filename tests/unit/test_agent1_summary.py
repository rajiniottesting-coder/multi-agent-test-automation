"""Agent 1's run summary prints every outcome, and the run is red when a
person has to act.

The duplicate guard refuses a story whose earlier run stopped part-way. Its
result carries no summary and no created keys, and the summary printer read
both unconditionally - so the refusal reached the log as
`KeyError: 'story_summary'` instead of what to do.
"""
from agents.agent1_analyst import print_summary

REFUSED = {"story_id": "X-1", "status": "partial_test_cases",
           "test_cases_generated": 0, "existing_test_cases": 3}
DONE = {"story_id": "X-2", "status": "already_processed",
        "test_cases_generated": 0, "existing_test_cases": 2}
CREATED = {"story_id": "X-3", "story_summary": "A story", "status": "success",
           "test_cases_generated": 2, "test_case_keys": ["X-4", "X-5"]}


def test_a_partial_set_is_explained_and_makes_the_run_red(capsys):
    assert print_summary([REFUSED]) is False
    out = capsys.readouterr().out
    assert "X-1" in out and "partial_test_cases" in out
    assert "Linked test cases already present: 3" in out
    assert "label the story ai-ready again" in out


def test_already_processed_is_a_clean_outcome(capsys):
    assert print_summary([DONE]) is True
    assert "already created" in capsys.readouterr().out


def test_a_normal_run_still_prints_what_it_created(capsys):
    assert print_summary([CREATED]) is True
    out = capsys.readouterr().out
    assert "X-3 — A story" in out and "X-4, X-5" in out


def test_a_failure_makes_the_run_red(capsys):
    assert print_summary([CREATED, {"story_id": "X-6", "status": "failed: ValueError"}]) is False
