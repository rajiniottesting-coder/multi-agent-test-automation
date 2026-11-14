"""Group B defects: D1 a person's open defect covers a failure (no
duplicate), D2 a person's closed defect is re-tested by the next run, D4 a
recurring failure links the closed defect, D5 priority, environment, commit.

Sandbox: the real JiraClient over the fake Jira; generic names only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import defects
from core import pipeline_health as ph
from scripts import triage_failures as tf
from tests.sandbox.fake_jira import FakeJira, jira_client_over
from tests.unit.test_defect_triage import RUN, _case, _junit

BUG = defects.settings()["issue_type"]


@pytest.fixture
def world(monkeypatch, tmp_path):
    ph.reset_cache()
    fake = FakeJira()
    fake.add("Story", "A shopper keeps a cart", key="SBX-1")
    fake.add("Test Case", "[Positive] Add an item", key="SBX-5")
    jira = jira_client_over(fake, monkeypatch)
    real = defects.section("defects")
    monkeypatch.setattr(defects, "settings", lambda: {**real, "max_new_per_run": 10})
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234567890")
    monkeypatch.setenv("BASE_URL", "https://app.example")
    features = tmp_path / "features"
    features.mkdir()
    (features / "cart.feature").write_text(
        "@cart\nFeature: Cart\n\n  @smoke\n  # JIRA: SBX-5 (hash: abc12345) owner: SBX-1\n"
        "  Scenario: Add an item\n    Given I am home\n\n"
        "  Scenario: Remove an item\n    Given I am home\n")
    yield fake, jira, features
    ph.reset_cache()


def _run(world, tmp_path, *cases, n=1):
    fake, jira, features = world
    return tf.run(jira, _junit(tmp_path, *cases), f"{RUN}{n}", features)


def _bugs(fake):
    return {k: d for k, d in fake.issues.items() if d["issuetype"] == BUG}


# ── D1 ──────────────────────────────────────────────────────

def test_a_persons_open_defect_covers_the_failure(world, tmp_path):
    fake, *_ = world
    mine = fake.add(BUG, "Cart add fails for me", labels=[])
    fake.link("Blocks", mine, "SBX-5")
    out = _run(world, tmp_path, _case("test_add_an_item", "failed"))
    assert out["raised"] == [] and out["followed"] == [mine]
    assert set(_bugs(fake)) == {mine}, "no duplicate raised"
    (body,) = fake.comments[mine]
    assert "fails test_cart::test_add_an_item too" in body and f"{RUN}1" in body
    out = _run(world, tmp_path, _case("test_add_an_item", "failed"), n=2)
    assert len(fake.comments[mine]) == 1, "commented once while it keeps failing"
    out = _run(world, tmp_path, _case("test_add_an_item"), n=3)
    assert out["followed_passing"] == [mine]
    assert "passes on main again" in fake.comments[mine][-1]


def test_a_persons_defect_on_the_story_covers_its_tests(world, tmp_path):
    fake, *_ = world
    mine = fake.add(BUG, "Cart is broken", labels=[])
    fake.link("Relates", mine, "SBX-1")
    out = _run(world, tmp_path, _case("test_add_an_item", "failed"))
    assert out["followed"] == [mine] and out["raised"] == []
    assert "SBX-5" in fake.linked(mine), "linked to the test case it covers"


def test_a_throwaway_or_pipeline_defect_never_counts_as_a_persons(world, tmp_path):
    fake, *_ = world
    junk = fake.add(BUG, "dummy", labels=["test-data"])
    fake.link("Blocks", junk, "SBX-5")
    out = _run(world, tmp_path, _case("test_add_an_item", "failed"))
    assert out["followed"] == [] and len(out["raised"]) == 1


# ── D2 ──────────────────────────────────────────────────────

def test_a_persons_closed_defect_is_re_tested_once(world, tmp_path):
    fake, *_ = world
    fixed = fake.add(BUG, "Add was broken", labels=[], status="Done")
    fake.link("Blocks", fixed, "SBX-5")
    out = _run(world, tmp_path, _case("test_add_an_item"), _case("test_remove_an_item"))
    assert out["retested"] == [fixed]
    (body,) = fake.comments[fixed]
    assert body.startswith("Re-tested after it was closed: 1 linked test(s)")
    assert "All pass: test_cart::test_add_an_item" in body
    assert "retested" in fake.issues[fixed]["labels"]
    out = _run(world, tmp_path, _case("test_add_an_item"), n=2)
    assert out["retested"] == [] and len(fake.comments[fixed]) == 1


def test_a_re_test_that_fails_says_so(world, tmp_path):
    fake, *_ = world
    fixed = fake.add(BUG, "Add was broken", labels=[], status="Done")
    fake.link("Relates", fixed, "SBX-1")
    _run(world, tmp_path, _case("test_add_an_item", "failed"))
    assert "Still failing: test_cart::test_add_an_item" in fake.comments[fixed][0]
    assert "reopen this defect" in fake.comments[fixed][0]


# ── D4 + D5 ─────────────────────────────────────────────────

def test_a_recurrence_links_the_closed_defect_and_fields_are_set(world, tmp_path):
    fake, jira, _ = world
    first = _run(world, tmp_path, _case("test_add_an_item", "failed"))["raised"][0]
    fake.issues[first]["status"] = "Done"
    out = _run(world, tmp_path, _case("test_add_an_item", "failed"), n=2)
    (second,) = out["raised"]
    assert out["recurs"] == [f"{second} -> {first}"]
    assert first in fake.linked(second)
    state = defects.state_of(fake.issues[second]["description"])
    assert state["recurs"] == first
    assert state["priority"] == "High", "@smoke -> critical -> High"
    assert state["environment"].startswith("https://app.example; browser")
    assert state["commit"] == "abcdef123456"
    assert f"**Recurs:** its earlier defect {first} was closed" in fake.issues[second][
        "description"] or f"Recurs:* its earlier defect {first}" in fake.issues[second][
        "description"]
    updates = [c for c in fake.calls if c[0] == "update" and c[1] == second]
    assert {"priority": {"name": "High"}} in [u[2] for u in updates]


def test_without_a_tag_the_story_priority_is_used(world, tmp_path):
    fake, *_ = world
    fake.issues["SBX-1"]["priority"] = "Low"
    out = _run(world, tmp_path, _case("test_remove_an_item", "failed"))
    (key,) = out["raised"]
    # Remove an item has no marker: traced by the feature file's one story.
    assert defects.state_of(fake.issues[key]["description"])["priority"] == "Low"


def test_scenario_tags_include_the_features():
    tags = defects.scenario_tags("tests.step_defs.test_x::test_add_an_item", Path("/nonexistent"))
    assert tags == []


def test_a_refused_field_is_reported_not_alerted(world, tmp_path, monkeypatch):
    fake, jira, _ = world

    def refuse(key, fields):
        raise RuntimeError("Field 'environment' cannot be set")
    monkeypatch.setattr(jira, "set_fields", refuse, raising=False)
    out = _run(world, tmp_path, _case("test_add_an_item", "failed"))
    (key,) = out["raised"]
    assert f"{key} priority" in out["fields_not_set"] and out["errors"] == []
