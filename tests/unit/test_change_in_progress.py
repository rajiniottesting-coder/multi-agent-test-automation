"""F-2 (G2): a test case is never revised by two changes at once.

Before: Agent 0 blocked a review row only when another story impacting the
test case had an OPEN PULL REQUEST. Two change stories approved for the same
test case before either had a PR could both revise it in Jira.

Now:
  * at analysis, a row is also blocked while another change is in progress:
    handed over and not finished (`impact-applied`, Impacts link, no PR yet),
    or with an open Impact Review that lists the test (`impact-proposed` - no
    link exists before the hand-over, so its report says so);
  * at hand-over (a review written BEFORE the other change was handed over),
    approving or retiring a test another change is still revising is refused;
    the scan retries by itself once that change merges or is undone.

Sandbox: real JiraClient over a fake Jira. Generic names only.
"""
from unittest.mock import MagicMock

import pytest

import agents.agent0_impact as a0
from core import impact_analysis as ia
from core.impact_handover import HandoverRefused, handover
from core.impact_settings import impact_settings
from tests.sandbox.fake_jira import jira_client_over
from tests.sandbox.seed import seed_jira

SETTINGS = impact_settings()
LABELS = SETTINGS["labels"]


@pytest.fixture
def world(monkeypatch):
    fake = seed_jira()                     # SBX-3 impacts SBX-12 (Impacts link), no labels
    fake.add("Story", "Change B", key="SBX-60", labels=[LABELS["check"]])
    return fake, jira_client_over(fake, monkeypatch)


def _cand(key):
    return ia.Candidate(id=key, ref=key, test_case_key=key, file="f.feature", title="t",
                        steps=[], layer=1)


def _blocks(jira, story="SBX-60", host=None, keys=("SBX-12",)):
    cands = [_cand(k) for k in keys]
    a0._owners_and_blocks(jira, host, story, cands, SETTINGS)
    return {c.test_case_key: c.blocked_by for c in cands}


# ── at analysis ──────────────────────────────────────────────────────────

def test_a_handed_over_change_without_a_pr_blocks_the_row(world):
    fake, jira = world
    assert _blocks(jira) == {"SBX-12": []}, "an impacting story not in progress: free"
    fake.issues["SBX-3"]["labels"].append(LABELS["applied"])
    assert _blocks(jira) == {"SBX-12": ["SBX-3"]}


def test_an_open_pr_still_blocks_as_before(world):
    fake, jira = world
    host = MagicMock()
    host.find_open_pr_for_story.side_effect = lambda s: {"number": 1} if s == "SBX-3" else None
    assert _blocks(jira, host=host) == {"SBX-12": ["SBX-3"]}


def _publish_review(fake, jira, story, key):
    """A real Impact Review for `story` listing `key`, as Agent 0 publishes it."""
    fake.add("Story", "Change A", key=story, labels=[LABELS["check"]])
    report = ia.report_dict(story, "h", "g", [
        {"key": key, "ref": key, "owner": "SBX-1", "tier": "must-update", "score": 0.9,
         "blocked_by": [], "file": "f.feature", "title": "t", "signals": {}, "paths": [],
         "reasons": []}], [], False, ia.Seeds(), [])
    live = dict(SETTINGS, shadow_mode=False)
    a0.publish(jira, story, report, live)
    assert LABELS["proposed"] in fake.issues[story]["labels"]


def test_an_open_review_that_lists_the_test_blocks_the_row(world):
    fake, jira = world
    _publish_review(fake, jira, "SBX-70", "SBX-13")
    assert _blocks(jira, keys=("SBX-13", "SBX-11")) == {"SBX-13": ["SBX-70"], "SBX-11": []}


def test_the_storys_own_open_review_never_blocks_it(world):
    fake, jira = world
    _publish_review(fake, jira, "SBX-70", "SBX-13")
    assert _blocks(jira, story="SBX-70", keys=("SBX-13",)) == {"SBX-13": []}


def test_the_checks_fail_open(world, monkeypatch):
    fake, jira = world
    fake.issues["SBX-3"]["labels"].append(LABELS["applied"])
    monkeypatch.setattr(jira, "get_story", MagicMock(side_effect=RuntimeError("down")))
    monkeypatch.setattr(jira, "find_stories_to_process", MagicMock(side_effect=RuntimeError("down")))
    assert _blocks(jira) == {"SBX-12": []}, "an API hiccup never blocks by itself"


def test_a_blocked_row_reaches_the_review_as_blocked(world):
    rows = a0._review_rows({"ranked": [{"key": "SBX-12", "owner": "SBX-1", "tier": "must-update",
                                         "score": 0.9, "blocked_by": ["SBX-3"], "signals": {},
                                         "paths": [], "reasons": [], "file": "f", "title": "t"}]})
    assert rows[0]["decision"] == "blocked by SBX-3"


# ── at hand-over ─────────────────────────────────────────────────────────

def test_handover_refuses_a_test_another_change_is_still_revising(world):
    fake, jira = world
    fake.issues["SBX-3"]["labels"].append(LABELS["applied"])
    with pytest.raises(HandoverRefused, match=r"SBX-12 by SBX-3 .*merge or be undone"):
        handover(jira, "SBX-60", {"SBX-12": "approve", "SBX-11": "reject"})
    assert not [l for l in fake.links.values() if l[1] == "SBX-60"], "nothing written"
    with pytest.raises(HandoverRefused):
        handover(jira, "SBX-60", {"SBX-12": "retire"}, dry_run=True)


def test_handover_goes_ahead_once_the_other_change_finished(world):
    fake, jira = world
    fake.issues["SBX-3"]["labels"].append(LABELS["applied"])
    result = handover(jira, "SBX-60", {"SBX-12": "reject"})
    assert result.rejected == ["SBX-12"], "a rejected row touches nothing: allowed"
    fake.issues["SBX-3"]["labels"].remove(LABELS["applied"])           # merged or undone
    result = handover(jira, "SBX-60", {"SBX-12": "approve"})
    assert result.approved == ["SBX-12"]


def test_the_storys_own_earlier_link_never_refuses_it(world):
    fake, jira = world
    fake.link("Impacts", "SBX-60", "SBX-11")          # its own earlier attempt
    fake.issues["SBX-60"]["labels"].append(LABELS["applied"])
    assert handover(jira, "SBX-60", {"SBX-11": "approve"}).approved == ["SBX-11"]


def test_the_scan_keeps_a_refused_handover_waiting(world, monkeypatch):
    fake, jira = world
    fake.issues["SBX-3"]["labels"].append(LABELS["applied"])
    fake.issues["SBX-60"]["labels"] = [LABELS["proposed"]]
    monkeypatch.setattr("core.impact_handover.decisions_from_review",
                        lambda tracker, story, settings=None: ("SBX-61", {"SBX-12": "approve"}))
    out = a0.hand_over_decided(jira, SETTINGS)
    assert out == [{"story": "SBX-60", "action": "waiting",
                    "why": "being revised by another change in progress: SBX-12 by SBX-3 - "
                           "wait for it to merge or be undone, or reject the row"}]
