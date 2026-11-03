"""A raised defect carries no code label (`ai-defect-<10 hex>`).

3 Nov 2026: the Jira label picker offered ai-defect-ff8881ed6e,
ai-defect-21bf9029c9, ... - one meaningless code per failing test and cause,
kept by the 14 closed defects too. The code was the triage's fingerprint: how
a repeat failure found its defect. Every defect's triage data already names
the test and the cause the fingerprint is computed from, so the triage now
reads it from there (core/defects.fingerprint_of); a defect raised before is
still found by its label, which goes on its next update;
scripts/tidy_defect_labels.py clears the rest. Generic keys only.
"""

import pytest

from core import defects
from scripts import tidy_defect_labels as tidy
from scripts import triage_failures as tf
from tests.sandbox.fake_jira import FakeJira, jira_client_over
from core import pipeline_health as ph
from core.ops_settings import DEFAULTS

TEST = "tests.step_defs.test_cart::test_add_an_item"
MULTI = "Error: strict mode violation: locator('.row') resolved to 3 elements"
CAUSE = "multi-match selector"
RUN = "https://ci.example/runs/"
# The shipped defaults, pinned: the tests do not follow a deployment's config.
S = {**DEFAULTS["defects"], "trace_owners": {}}


def _case(name, outcome="passed"):
    body = {"passed": "", "failed": f'<failure message="{MULTI}">{MULTI}</failure>'}[outcome]
    props = '<properties><property name="retried" value="1"/></properties>' if body else ""
    return (f'<testcase classname="tests.step_defs.test_cart" name="{name}">{props}{body}'
            "</testcase>")


@pytest.fixture
def world(monkeypatch, tmp_path):
    ph.reset_cache()
    monkeypatch.setattr(defects, "settings", lambda: S)
    fake = FakeJira()
    fake.add("Story", "A shopper keeps a cart", key="SBX-1")
    fake.add("Test Case", "[Positive] Add an item", key="SBX-5")
    jira = jira_client_over(fake, monkeypatch)
    features = tmp_path / "features"
    features.mkdir()
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-5 (hash: abc12345) owner: SBX-1\n"
        "  Scenario: Add an item\n    Given I am home\n")
    yield fake, jira, features
    ph.reset_cache()


def _run(world, tmp_path, n, *cases):
    fake, jira, features = world
    p = tmp_path / "junit.xml"
    p.write_text(f'<testsuites><testsuite>{"".join(cases)}</testsuite></testsuites>')
    return tf.run(jira, p, f"{RUN}{n}", features)


def _bugs(fake):
    return {k: d for k, d in fake.issues.items() if d["issuetype"] == "Bug"}


def _state(**kw):
    base = {"test": TEST, "test_case": "SBX-5", "owner": "SBX-1", "cause": CAUSE,
            "cause_text": "x", "remedy": "y", "failure": MULTI, "times": 2,
            "first_seen": "2026-10-01", "last_seen": "2026-10-02", "last_run": f"{RUN}0"}
    base.update(kw)
    return base


def _all_labels(fake):
    return {lb for d in fake.issues.values() for lb in d["labels"]}


# ── the triage ──────────────────────────────────────────────────────────────

def test_a_new_defect_carries_no_code_label_and_is_found_again(world, tmp_path):
    fake, *_ = world
    _run(world, tmp_path, 1, _case("test_add_an_item", "failed"))
    (key, bug), = _bugs(fake).items()
    assert bug["labels"] == ["ai-defect"]
    assert not defects.legacy_labels(_all_labels(fake), S)
    out = _run(world, tmp_path, 2, _case("test_add_an_item", "failed"))
    assert out["raised"] == [] and out["updated"] == [key], "found by its triage data"
    assert defects.state_of(fake.issues[key]["description"])["times"] == 2
    out = _run(world, tmp_path, 3, _case("test_add_an_item"))
    assert out["passing"] == [key], "passing again still flagged"


def test_another_cause_of_the_same_test_is_another_defect(world, tmp_path):
    fake, *_ = world
    other = fake.add("Bug", "[Auto] old", labels=["ai-defect"],
                     description=defects.render(None, _state(cause="unclassified")))
    out = _run(world, tmp_path, 1, _case("test_add_an_item", "failed"))
    assert len(out["raised"]) == 1 and other not in out["updated"]


def test_a_defect_raised_before_loses_its_code_label_on_its_next_update(world, tmp_path):
    fake, *_ = world
    label = defects.defect_label(TEST, CAUSE, S)
    old = fake.add("Bug", "[Auto] old", labels=["ai-defect", label, "ai-defect-passing"],
                   description=defects.render(None, _state()))
    out = _run(world, tmp_path, 1, _case("test_add_an_item", "failed"))
    assert out["raised"] == [] and out["updated"] == [old]
    assert label not in fake.issues[old]["labels"]
    assert "ai-defect" in fake.issues[old]["labels"]
    assert out["failing_again"] == [old], "the passing label is not a code label"


def test_a_defect_whose_data_was_edited_away_is_still_found_by_its_label(world, tmp_path):
    fake, *_ = world
    label = defects.defect_label(TEST, CAUSE, S)
    old = fake.add("Bug", "[Auto] old", labels=["ai-defect", label],
                   description="A person rewrote this description.")
    out = _run(world, tmp_path, 1, _case("test_add_an_item", "failed"))
    assert out["raised"] == [] and out["updated"] == [old], "no duplicate"


def test_a_defect_with_neither_is_left_alone(world, tmp_path):
    fake, *_ = world
    stray = fake.add("Bug", "[Auto] stray", labels=["ai-defect"], description="no data")
    assert defects.open_defects(world[1], S) == {}
    out = _run(world, tmp_path, 1, _case("test_add_an_item", "failed"))
    assert stray not in out["updated"] and len(out["raised"]) == 1


def test_the_fingerprint_is_the_one_the_label_carried():
    issue = {"description": defects.render(None, _state()), "labels": ["ai-defect"]}
    assert defects.fingerprint_of(issue, S) == defects.defect_label(TEST, CAUSE, S)


@pytest.mark.parametrize("labels, legacy", [
    (["ai-defect", "ai-defect-0123456789"], ["ai-defect-0123456789"]),
    (["ai-defect-passing", "ai-defect-unmapped", "ai-defect-0123abcd"], []),
    (["ai-defect-0123456789a", "x-ai-defect-0123456789"], []),
])
def test_only_a_ten_hex_code_is_a_code_label(labels, legacy):
    assert defects.legacy_labels(labels, S) == legacy


# ── the tidy pass ───────────────────────────────────────────────────────────

def _seed(fake):
    lab = lambda t: defects.defect_label(t, CAUSE, S)          # noqa: E731
    readable = fake.add("Bug", "a", labels=["ai-defect", lab("t1")],
                        description=defects.render(None, _state(test="t1")))
    closed = fake.add("Bug", "b", labels=["ai-defect", lab("t2"), "ai-defect-passing"],
                      description="edited", status="Done")
    stuck = fake.add("Bug", "c", labels=["ai-defect", lab("t3")], description="edited")
    clean = fake.add("Bug", "d", labels=["ai-defect"],
                     description=defects.render(None, _state(test="t4")))
    return readable, closed, stuck, clean


def test_the_tidy_pass_lists_and_changes_nothing_by_default(world, capsys):
    fake, jira, _ = world
    _seed(fake)
    before = {k: list(d["labels"]) for k, d in fake.issues.items()}
    out = tidy.run(jira, S, apply=False)
    assert {k: list(d["labels"]) for k, d in fake.issues.items()} == before
    assert len(out["remove"]) == 2 and len(out["keep"]) == 1
    assert "Run with --apply" in capsys.readouterr().out


def test_the_tidy_pass_removes_what_is_no_longer_needed(world):
    fake, jira, _ = world
    readable, closed, stuck, clean = _seed(fake)
    out = tidy.run(jira, S, apply=True)
    assert fake.issues[readable]["labels"] == ["ai-defect"]
    assert fake.issues[closed]["labels"] == ["ai-defect", "ai-defect-passing"]
    assert defects.legacy_labels(fake.issues[stuck]["labels"], S), \
        "open and unreadable: the label is how the triage finds it"
    assert fake.issues[clean]["labels"] == ["ai-defect"] and out["refused"] == []


def test_a_refused_removal_is_listed_not_raised(world, monkeypatch):
    fake, jira, _ = world
    _seed(fake)

    def refuse(*a, **k):
        raise RuntimeError("403")
    monkeypatch.setattr(jira, "remove_label", refuse)
    out = tidy.run(jira, S, apply=True)
    assert len(out["refused"]) == 2


def test_the_tidy_script_needs_no_application_name():
    from pathlib import Path
    text = Path(tidy.__file__).read_text(encoding="utf-8")
    assert "ai-defect" not in text.split('"""', 2)[2], "the label comes from the settings"
