"""Agent 4 tests a pull request MERGED WITH MAIN, not the branch alone.

On a pull_request event GitHub takes the workflow file from the merge result
(refs/pull/<n>/merge). Agent 4 then checked out the branch alone
(pull_request.head.ref), so an older branch ran main's workflow with its own,
older scripts: PR #241 (3 Nov 2026) went red on "unrecognized arguments:
--app-probe" while every test passed - main had changed the workflow and its
script together after the branch was cut.

Now both jobs check out the event's commit - the merge result on a pull
request, the event's own commit otherwise: one run per push as before, the
workflow and the code always from the same commit, and the result is what main
will hold after the merge. Nothing that needs the branch's NAME reads it from
the checkout (GITHUB_HEAD_REF / github.head_ref still name it).

By SHA (github.sha), not by github.ref's name: GitHub deletes
refs/pull/<n>/merge when the pull request is merged or closed, so a run still
going when #253 was merged (3 Nov 2026) could not check out its report job
("couldn't find remote ref refs/pull/253/merge") and Agent 5's report was
lost. The commit stays fetchable.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "agent4_runner.yml"


def _jobs():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))["jobs"]


def _checkouts(job):
    return [s for s in job.get("steps") or [] if "actions/checkout" in str(s.get("uses", ""))]


def test_the_tests_and_the_report_run_on_the_merge_result():
    jobs = _jobs()
    for name in ("test", "report"):
        (checkout,) = _checkouts(jobs[name])
        assert (checkout.get("with") or {}).get("ref") == "${{ github.sha }}", \
            f"{name}: the same commit the workflow came from, by SHA"


def test_no_job_checks_out_a_ref_that_merging_deletes():
    for name, job in _jobs().items():
        for checkout in _checkouts(job):
            ref = str((checkout.get("with") or {}).get("ref", ""))
            assert "github.ref" not in ref and "/merge" not in ref, \
                f"{name}: refs/pull/<n>/merge is gone once the pull request merges"


def test_no_job_checks_out_the_branch_alone():
    for name, job in _jobs().items():
        for checkout in _checkouts(job):
            ref = str((checkout.get("with") or {}).get("ref", ""))
            assert "head.ref" not in ref and "head.sha" not in ref, \
                f"{name}: the branch alone runs main's workflow with older scripts"


def test_the_defect_triage_still_reads_main():
    (checkout,) = _checkouts(_jobs()["triage"])
    assert checkout["with"]["ref"] == "main"


def test_the_branch_name_still_comes_from_the_event():
    steps = _jobs()["test"]["steps"]
    wait = next(s for s in steps if "Wait for earlier pull requests" in (s.get("name") or ""))
    assert wait["env"]["BRANCH"] == "${{ github.head_ref || github.ref_name }}"
    reporter = (ROOT / "agents" / "agent5_reporter.py").read_text(encoding="utf-8")
    assert 'os.getenv("GITHUB_HEAD_REF")' in reporter
