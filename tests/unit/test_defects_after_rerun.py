"""A defect only after a failed rerun (defects.only_after_retry).

Asked by the repository owner after 30 Oct 2026, when one nightly run on main -
17 of 17 failing on an application that was not itself - raised ten defects
from its first run alone: rerun the failed tests, and raise a defect only
after the rerun.

Now the triage (core/defects.py, scripts/triage_failures.py) raises or updates
a defect only for a test that failed, was run again and failed again
(`retried`). A failure that was not run again raises nothing, leaves an open
defect as it is, and is listed in one `failures-not-retried` health alert,
which closes on the next run where every failure was run again. The rule can
be switched off. Sandbox: the real JiraClient over a fake Jira; generic names.
"""
import json
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import pytest

from core import defects
from core import pipeline_health as ph
from scripts import triage_failures as tf
from tests.sandbox.fake_jira import FakeJira, jira_client_over


def _junit(*cases):
    body = []
    for name, outcome, msg, props in cases:
        p = "".join(f'<property name="{k}" value="{v}"/>' for k, v in (props or {}).items())
        m = escape(msg, {'"': "&quot;"})
        fail = f'<failure message="{m}">{m}</failure>' if outcome == "failed" else ""
        body.append(f'<testcase classname="tests.step_defs.test_x" name="{name}">'
                    + (f"<properties>{p}</properties>" if p else "") + fail + "</testcase>")
    return ET.fromstring(f"<testsuites><testsuite>{''.join(body)}</testsuite></testsuites>")


@pytest.fixture
def world(monkeypatch, tmp_path):
    ph.reset_cache()
    fake = FakeJira()
    jira = jira_client_over(fake, monkeypatch)
    features = tmp_path / "features"
    features.mkdir()
    yield fake, jira, features
    ph.reset_cache()


def _run(world, tmp_path, root, n=1, probe=None):
    fake, jira, features = world
    d = tmp_path / f"run{n}"
    d.mkdir()
    ET.ElementTree(root).write(d / "junit.xml")
    if probe is not None:
        (d / "app_probe.json").write_text(json.dumps(probe))
    return tf.run(jira, d / "junit.xml", f"https://ci.example/runs/{n}", features)


def _bugs(fake):
    return [k for k, d in fake.issues.items() if d["issuetype"] == "Bug"]


def _alerts(fake):
    key = next((k for k, d in fake.issues.items() if "pipeline-health" in d["labels"]), None)
    return fake.comments.get(key, []) if key else []


def test_a_failure_not_run_again_raises_no_defect_and_one_alert(world, tmp_path):
    fake, *_ = world
    out = _run(world, tmp_path, _junit(("test_a", "failed", "TimeoutError: x", None)))
    assert out["raised"] == [] and _bugs(fake) == []
    assert out["not_retried"] == ["tests.step_defs.test_x::test_a"]
    (alert,) = _alerts(fake)
    assert alert.startswith(f"[health:open] {tf.NOT_RETRIED}") and "test_a" in alert


def test_a_failure_that_failed_again_raises_its_defect_and_the_alert_closes(world, tmp_path):
    fake, *_ = world
    _run(world, tmp_path, _junit(("test_a", "failed", "TimeoutError: x", None)), n=1)
    out = _run(world, tmp_path, _junit(("test_a", "failed", "TimeoutError: x",
                                        {"retried": "1"})), n=2)
    assert len(out["raised"]) == 1 and out["not_retried"] == []
    assert _alerts(fake)[-1].startswith(f"[health:resolved] {tf.NOT_RETRIED}")


def test_an_open_defect_is_neither_updated_nor_flagged_by_a_failure_not_run_again(world, tmp_path):
    fake, *_ = world
    _run(world, tmp_path, _junit(("test_a", "failed", "TimeoutError: x", {"retried": "1"})), n=1)
    (key,) = _bugs(fake)
    before = fake.issues[key]["description"]
    out = _run(world, tmp_path, _junit(("test_a", "failed", "TimeoutError: x", None)), n=2)
    assert out["updated"] == [] and out["passing"] == []
    assert fake.issues[key]["description"] == before


def test_the_rule_can_be_switched_off(world, tmp_path, monkeypatch):
    real = defects.section("defects")
    monkeypatch.setattr(defects, "settings", lambda: {**real, "only_after_retry": False})
    out = _run(world, tmp_path, _junit(("test_a", "failed", "TimeoutError: x", None)))
    assert len(out["raised"]) == 1 and out["not_retried"] == []
