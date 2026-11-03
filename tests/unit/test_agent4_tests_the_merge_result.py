"""Agent 4 tests a pull request MERGED WITH MAIN, not the branch alone.

On a pull_request event GitHub takes the workflow file from the merge result
(refs/pull/<n>/merge). Agent 4 then checked out the branch alone
(pull_request.head.ref), so an older branch ran main's workflow with its own,
older scripts: PR #241 (3 Nov 2026) went red on "unrecognized arguments:
--app-probe" while every test passed - main had changed the workflow and its
script together after the branch was cut.

Now both jobs check out github.ref - the merge result on a pull request, the
event's own ref otherwise: one run per push as before, the workflow and the
code always from the same commit, and the result is what main will hold after
the merge. Nothing that needs the branch's NAME reads it from the checkout
(GITHUB_HEAD_REF / github.head_ref still name it).
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
        assert (checkout.get("with") or {}).get("ref") == "${{ github.ref }}", \
            f"{name}: the same commit the workflow came from"


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
