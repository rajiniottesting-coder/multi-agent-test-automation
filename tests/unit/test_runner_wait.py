"""F-5 (M3, M4): Agent 3 waits long enough for Agent 4's result.

Before: when the only blocking finding was a predicted test failure, Agent 3
waited 8 minutes for Agent 4's run on the same commit. Agent 4 first waits its
turn for the shared browser (up to 15 minutes) and then runs the suite, so a
queued run often finished after Agent 3 had given up - the prediction kept
blocking without evidence (safe, but less accurate).

Now the wait is Agent 4's turn cap plus one full run, kept equal to the
workflows by the checks below, and Agent 3's job timeout fits it.
"""
import re

import agents.agent3_reviewer as a3


def _yaml(path):
    return open(path, encoding="utf-8").read()


def test_the_wait_is_the_turn_cap_plus_one_run():
    turn = int(re.search(r'MAX_WAIT_SECONDS:\s*"(\d+)"',
                         _yaml(".github/workflows/agent4_runner.yml")).group(1))
    assert a3.E2E_TURN_CAP_SECONDS == turn
    assert a3.RUNNER_WAIT_SECONDS == turn + a3.E2E_RUN_SECONDS
    assert a3.E2E_RUN_SECONDS >= 7 * 60, "a run measured at the 90th percentile fits"


def test_agent3s_job_outlives_its_wait():
    wf = _yaml(".github/workflows/agent3-reviewer.yml")
    timeout = int(re.search(r"timeout-minutes:\s*(\d+)", wf).group(1)) * 60
    assert timeout >= a3.RUNNER_WAIT_SECONDS + 5 * 60, "setup and the review call fit too"


class _Host:
    """A runner run on the PR's head that completes at `done_at` seconds."""

    def __init__(self, clock, done_at):
        self.clock, self.done_at = clock, done_at

    def list_open_prs(self):
        return [{"number": 7, "head_sha": "abc"}]

    def get_workflow_runs(self, workflow, branch):
        status = "completed" if self.clock() >= self.done_at else "queued"
        return [{"head_sha": "abc", "status": status, "conclusion": "success", "id": 1}]


def _wait(done_at, wait_seconds=a3.RUNNER_WAIT_SECONDS):
    now = {"t": 0}
    clock = lambda: now["t"]

    def sleep(s):
        now["t"] += s
    return a3._completed_runner_run(_Host(clock, done_at), 7, "auto/X-1-x", wait_seconds,
                                    a3.RUNNER_POLL_SECONDS, sleep=sleep, clock=clock)


def test_a_run_that_waited_its_turn_is_still_read():
    """Queued 14 minutes behind other PRs, then 5 minutes of tests."""
    assert _wait(19 * 60) is not None
    assert _wait(19 * 60, wait_seconds=480) is None, "the old 8-minute wait gave up on it"


def test_past_the_wait_it_still_gives_up():
    assert _wait(a3.RUNNER_WAIT_SECONDS + 120) is None
