"""F-19: a failed test is retried once; a pass on the retry is a recorded flake.

Before: a failure was a failure on the first try (only a named 5xx/429 was
re-run). A test that fails one run in ten turned PRs red for nothing, and
nothing counted how often - the next person paid for it again.

Now Agent 4 retries the remaining failures once (`--last-failed`, at most
MAX_RETRIED_TESTS). scripts/finalise_junit.py merges the retry: a pass is
`flaky` (counts as passed) or `outage_recovered` when the first failure was the
application's outage; a second failure is `retried` and stays a failure. The
job's result is decided after the retry. Flakes are named in the run summary
and Agent 5's report and recorded on the pipeline health issue
(core/flaky_tests.py), never raised as defects. Quarantine is a later step.
"""
import datetime as dt
import os
import re
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import agents.agent5_reporter as a5
from core import flaky_tests
from core import junit_marks as jm
from core import pipeline_health as ph
from scripts import finalise_junit as fj
from tests.sandbox.fake_jira import FakeJira, jira_client_over

ROOT = Path(__file__).resolve().parents[2]
NAV_503 = ("AssertionError: Navigation to https://s.example/x returned HTTP 503 (x) after 3 "
           "attempts. The page did not load, so every selector on it will time out.")


def _case(name, outcome="passed", msg="AssertionError: boom", props=None):
    body = {"passed": "", "failed": f'<failure message="{msg}">tb</failure>',
            "error": f'<error message="{msg}">tb</error>', "skipped": "<skipped/>"}[outcome]
    p = "".join(f'<property name="{k}" value="{v}"/>' for k, v in (props or {}).items())
    return (f'<testcase classname="tests.step_defs.test_m" name="{name}">'
            + (f"<properties>{p}</properties>" if p else "") + body + "</testcase>")


def _junit(*cases):
    return ET.fromstring(f'<testsuites><testsuite tests="0">{"".join(cases)}</testsuite></testsuites>')


def _by_name(root):
    return {c.get("name"): c for c in jm.cases(root)}


# ── the merge ────────────────────────────────────────────────

def test_a_pass_on_the_retry_is_flaky_and_counts_as_passed():
    root = _junit(_case("a", "failed", props={"reruns": "2"}), _case("b"))
    out = fj.merge_retry(root, _junit(_case("a")))
    a = _by_name(root)["a"]
    assert out["flaky"] == ["tests.step_defs.test_m::a"]
    assert jm.is_flaky(a) and jm.outcome(a) == "passed"
    assert jm.props(a)["first_failure"] == "AssertionError: boom"
    assert jm.props(a)["reruns"] == "2", "what the first run learned is kept"
    suite = root.find("testsuite")
    assert (suite.get("tests"), suite.get("failures"), suite.get("errors")) == ("2", "0", "0")
    assert [c.get("name") for c in jm.cases(root)] == ["a", "b"], "order kept"


def test_a_pass_after_an_outage_is_not_a_flake():
    root = _junit(_case("a", "failed", msg=NAV_503.replace('"', "'")))
    out = fj.merge_retry(root, _junit(_case("a")))
    a = _by_name(root)["a"]
    assert out["outage_recovered"] and not out["flaky"]
    assert not jm.is_flaky(a) and jm.props(a)["outage_recovered"] == "1"


def test_a_second_failure_stays_a_failure_with_the_newest_evidence():
    root = _junit(_case("a", "failed", msg="first"))
    fj.merge_retry(root, _junit(_case("a", "error", msg="second")))
    a = _by_name(root)["a"]
    assert jm.outcome(a) == "error" and "second" in jm.failure_text(a)
    assert jm.props(a)["retried"] == "1" and jm.props(a)["first_failure"] == "first"
    assert root.find("testsuite").get("errors") == "1"


def test_a_test_the_retry_did_not_run_or_skipped_is_left_alone():
    root = _junit(_case("a", "failed"), _case("b", "failed"))
    out = fj.merge_retry(root, _junit(_case("b", "skipped")))
    assert out == {"flaky": [], "outage_recovered": [], "retried": []}
    assert all(jm.outcome(c) == "failed" for c in jm.cases(root))


def test_a_passing_test_is_never_replaced():
    root = _junit(_case("a"))
    fj.merge_retry(root, _junit(_case("a", "failed")))
    assert jm.outcome(_by_name(root)["a"]) == "passed" and not jm.props(_by_name(root)["a"])


def test_finalise_marks_outages_after_the_merge():
    root = _junit(_case("a", "failed"), _case("b", "failed"))
    out = fj.finalise(root, _junit(_case("a", "failed", msg=NAV_503.replace('"', "'"))))
    assert out["retried"] == ["tests.step_defs.test_m::a"] and out["outage"] == [
        "tests.step_defs.test_m::a"]
    assert jm.is_outage(_by_name(root)["a"]) and not jm.is_outage(_by_name(root)["b"])


def test_the_cli_without_a_retry_file_only_marks(tmp_path):
    p = tmp_path / "junit.xml"
    p.write_text(ET.tostring(_junit(_case("a", "failed")), encoding="unicode"))
    assert fj.main([str(p), "--retry", str(tmp_path / "absent.xml")]) == 0
    assert jm.outcome(jm.cases(ET.parse(p).getroot())[0]) == "failed"


# ── counting and the verdict ─────────────────────────────────

def _file(tmp_path, root, name="junit.xml"):
    p = tmp_path / name
    p.write_text(ET.tostring(root, encoding="unicode"))
    return p


def test_count_failed(tmp_path, capsys):
    p = _file(tmp_path, _junit(_case("a", "failed"), _case("b", "error"), _case("c")))
    assert fj.count_failed(p) == 2 and fj.count_failed(tmp_path / "none.xml") == 0
    fj.main(["--count-failed", str(p)])
    assert capsys.readouterr().out.strip() == "2"


@pytest.mark.parametrize("cases, code, expected, says", [
    ([("a", "passed", {})], "0", 0, "all 1 tests passed"),
    ([("a", "passed", {"flaky": "1"})], "1", 0, "1 passed only on the retry"),
    ([("a", "failed", {})], "1", 1, "1 failed of 1"),
    ([("a", "failed", {"outage": "1"}), ("b", "passed", {})], "1", 1,
     "1 not judged (application unavailable) of 2"),
    ([("a", "passed", {})], "2", 1, "interrupted"),
    ([("a", "passed", {})], "5", 1, "no tests collected"),
    ([], "0", 1, "no tests"),
    ([("a", "passed", {})], "", 0, "all 1"),
])
def test_the_verdict(tmp_path, cases, code, expected, says):
    p = _file(tmp_path, _junit(*[_case(n, o, props=pr) for n, o, pr in cases]))
    result, reason = fj.verdict(p, code)
    assert result == expected and says in reason


def test_no_report_fails_the_verdict(tmp_path):
    assert fj.verdict(tmp_path / "junit.xml", "1")[0] == 1
    assert fj.main(["--verdict", str(tmp_path / "junit.xml"), "--exit-code", "0"]) == 1


# ── real pytest: the run, the retry with --last-failed, the merge ─────────

def test_real_pytest_retry_round_trip(tmp_path):
    proj = tmp_path / "proj"
    (proj / "t").mkdir(parents=True)
    (proj / "pytest.ini").write_text("[pytest]\n")
    (proj / "t" / "test_x.py").write_text(textwrap.dedent('''
        from pathlib import Path
        FLAG = Path(__file__).with_name("seen")

        def test_flaky():
            if not FLAG.exists():
                FLAG.write_text("1")
                assert False, "first time only"

        def test_broken():
            assert 1 == 2

        def test_fine():
            pass
    '''))
    run = lambda *a: subprocess.run([sys.executable, "-m", "pytest", "t", "-q", "-p",
                                     "no:randomly", *a], cwd=proj, capture_output=True,
                                    text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    first = run("--junit-xml=junit.xml")
    assert first.returncode == 1
    assert fj.count_failed(proj / "junit.xml") == 2
    run("--last-failed", "--last-failed-no-failures", "none", "--junit-xml=junit-retry.xml")
    retry = ET.parse(proj / "junit-retry.xml").getroot()
    assert {c.get("name") for c in jm.cases(retry)} == {"test_flaky", "test_broken"}, \
        "--last-failed reran exactly the failures"
    assert fj.main([str(proj / "junit.xml"), "--retry", str(proj / "junit-retry.xml")]) == 0
    final = _by_name(ET.parse(proj / "junit.xml").getroot())
    assert jm.is_flaky(final["test_flaky"])
    assert jm.props(final["test_broken"])["retried"] == "1"
    assert jm.outcome(final["test_fine"]) == "passed"
    assert fj.verdict(proj / "junit.xml", str(first.returncode)) == (1, "1 failed of 3 after the retry")
    (proj / "t" / "test_x.py").write_text((proj / "t" / "test_x.py").read_text()
                                          .replace("assert 1 == 2", "pass"))
    # had the broken test passed on the retry too, the job would be green
    run("--last-failed", "--last-failed-no-failures", "none", "--junit-xml=junit-retry.xml")
    fj.main([str(proj / "junit.xml"), "--retry", str(proj / "junit-retry.xml")])
    assert fj.verdict(proj / "junit.xml", "1")[0] == 0


# ── the workflow ─────────────────────────────────────────────

def _steps():
    import yaml
    wf = yaml.safe_load((ROOT / ".github/workflows/agent4_runner.yml").read_text(encoding="utf-8"))
    return wf["jobs"]["test"], wf["jobs"]["test"]["steps"]


def _named(steps, fragment):
    return next(s for s in steps if fragment in (s.get("name") or ""))


def test_the_workflow_runs_retries_merges_and_decides_in_that_order():
    job, steps = _steps()
    names = [s.get("name") or "" for s in steps]
    order = ["Run app tests", "Keep only the final attempt", "Retry failed tests once",
             "Mark what the run learned", "Write test summary", "Decide the E2E result"]
    idx = [next(i for i, n in enumerate(names) if frag in n) for frag in order]
    assert idx == sorted(idx)
    assert names[-1].startswith("Decide the E2E result"), "the result is decided last"
    run = _named(steps, "Run app tests")
    assert run["id"] == "e2e" and "set +e" in run["run"] and "exit_code=$code" in run["run"]
    retry = _named(steps, "Retry failed tests once")
    assert "steps.e2e.outputs.exit_code == '1'" in retry["if"]
    assert "--last-failed" in retry["run"] and "junit-retry.xml" in retry["run"]
    assert set(_named(steps, "Run app tests")["env"]) <= set(retry["env"]), \
        "the retry logs in like the run"
    assert "--retry reports/junit-retry.xml" in _named(steps, "Mark what the run learned")["run"]
    decide = _named(steps, "Decide the E2E result")
    assert "--verdict" in decide["run"] and "steps.e2e.outputs.exit_code" in decide["run"]
    assert int(job["timeout-minutes"]) >= 40


def test_the_summary_names_flakes(tmp_path):
    step = _named(_steps()[1], "Write test summary")
    script = textwrap.dedent(re.search(r"<<\s*'PYEOF'\n(.*?)\n\s*PYEOF", step["run"], re.S).group(1))
    p = _file(tmp_path, _junit(_case("a", props={"flaky": "1", "first_failure": "boom once"}),
                               _case("b")))
    root = ET.parse(p).getroot()
    jm.recount(root)
    p.write_text(ET.tostring(root, encoding="unicode"))
    out = tmp_path / "s.md"
    subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True, capture_output=True,
                   env={**os.environ, "GITHUB_STEP_SUMMARY": str(out),
                        "SUMMARY_REPORTS": f"{p}|App Tests (E2E)", "E2E_EVENT": "pull_request"})
    text = out.read_text(encoding="utf-8")
    assert "All 2 tests passed (1 only on the retry - flaky)" in text
    assert "Passed only on the retry (flaky)" in text and "boom once" in text


# ── the record on the health issue ───────────────────────────

NOW = dt.datetime(2026, 10, 27, 9, tzinfo=dt.timezone.utc)


@pytest.fixture
def world(monkeypatch):
    ph.reset_cache()
    fake = FakeJira()
    yield fake, jira_client_over(fake, monkeypatch)
    ph.reset_cache()


def test_flakes_are_counted_per_test_in_the_window(world):
    fake, jira = world
    assert flaky_tests.record(jira, [("m::a", "boom"), ("m::b", None)], "run/1", NOW) == 2
    flaky_tests.record(jira, [("m::a", "boom")], "run/2", NOW)
    flaky_tests.record(jira, [("m::c", "x")], "run/0", NOW - dt.timedelta(days=40))
    key = ph.issue_key(jira)
    assert flaky_tests.summary(jira, key, NOW) == [("m::a", 2, "2026-10-27"),
                                                   ("m::b", 1, "2026-10-27")]
    desc = fake.issues[key]["description"]
    assert "Flaky tests (last 30 days)" in desc and "{{m::a}}" in desc
    assert not [c for c in fake.comments.get(key, [])], "a flake posts no comment"


def test_prune_drops_old_flakes_and_their_names(world):
    fake, jira = world
    flaky_tests.record(jira, [("m::old", "x")], "r", NOW - dt.timedelta(days=40))
    flaky_tests.record(jira, [("m::new", "x")], "r", NOW)
    assert flaky_tests.prune(jira, NOW) == 1
    keys = jira.property_keys(ph.issue_key(jira))
    assert any(flaky_tests.hash_of("m::new") in k for k in keys)
    assert not any(flaky_tests.hash_of("m::old") in k for k in keys)


def test_nothing_to_record_and_disabled_write_nothing(world, monkeypatch):
    fake, jira = world
    assert flaky_tests.record(jira, [], "r") == 0
    monkeypatch.setattr(flaky_tests, "section", lambda name: {"enabled": False})
    assert flaky_tests.record(jira, [("m::a", "x")], "r") == 0
    assert fake.issues == {}


# ── Agent 5 ──────────────────────────────────────────────────

def test_agent5_reads_and_names_the_flake(tmp_path, world):
    fake, jira = world
    p = _file(tmp_path, _junit(_case("a", props={"flaky": "1", "first_failure": "boom"}),
                               _case("b")))
    report = a5.parse_junit_xml(p)
    (flaky,) = [r for r in report.results if r.flaky]
    assert flaky.status == "passed" and flaky.first_failure == "boom"
    body = a5.build_final_comment("prose", report)
    assert "Passed only on the retry (flaky)" in body and "`test_m::a` - first failure: boom" in body
    assert a5.record_flakes(jira, report.results, "run/9") == 1


def test_agent5_without_flakes_is_unchanged(tmp_path):
    report = a5.parse_junit_xml(_file(tmp_path, _junit(_case("b"))))
    assert "flaky" not in a5.build_final_comment("prose", report)


def test_agent5_flake_recording_never_fails_the_report(monkeypatch):
    monkeypatch.setattr(flaky_tests, "record", lambda *a: (_ for _ in ()).throw(OSError("x")))
    from core.schemas import TestResult as Result
    r = Result(name="a", classname="m", status="passed", flaky=True)
    assert a5.record_flakes(object(), [r], None) == 0
