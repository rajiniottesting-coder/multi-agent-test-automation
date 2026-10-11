"""
C1 and C2 (Agent 0 design): Agent 1 cannot start early, and the hand-over.

Formats are unit-tested; the hand-over itself runs end to end in the sandbox
(the real JiraClient against tests/sandbox/fake_jira.FakeJira).
"""
import pytest

from core import impact_review, impact_trace
from core.impact_handover import HandoverRefused, decisions_from_review, handover
from core.impact_settings import DEFAULTS, impact_settings
from tests.sandbox.fake_jira import jira_client_over
from tests.sandbox.seed import seed_jira


# ─────────────────────────────────────────────────────────────────
# formats
# ─────────────────────────────────────────────────────────────────
class TestReviewTable:
    ROWS = [{"key": "AB-3", "owner": "AB-1", "tier": "must-update", "score": 0.9,
             "evidence": "login:error | used by step"},
            {"key": "AB-4", "owner": "AB-1", "tier": "review", "score": 0.4, "evidence": ""}]

    def test_render_defaults_and_round_trip(self):
        text = impact_review.render("AB-9", self.ROWS)
        assert "||Test case||Owner||Tier||Score||Evidence||Decision||" in text
        assert impact_review.parse(text) == {"AB-3": "approve", "AB-4": "?"}
        assert "login:error / used by step" in text           # pipes cannot break the row

    def test_reviewer_edits_are_read_by_key_and_last_cell(self):
        text = impact_review.render("AB-9", self.ROWS)
        text = text.replace("|AB-4|AB-1|review|0.4|-|?|", "|AB-4|AB-1|review|0.4|checked it| Retire |")
        assert impact_review.parse(text) == {"AB-3": "approve", "AB-4": "retire"}

    def test_unknown_words_are_undecided(self):
        assert impact_review.parse("|AB-3|x|maybe|") == {"AB-3": "?"}
        assert impact_review.undecided({"AB-3": "?", "AB-4": "reject"}) == ["AB-3"]


class TestTraceFormats:
    def test_will_revise_parses_and_dedupes(self):
        body = impact_trace.will_revise("AB-9", "New rule", ["AB-3"], ["AB-6"], review="AB-50")
        assert impact_trace.parse(body) == {"kind": "will-revise", "change": "AB-9", "ref": "AB-50"}
        assert impact_trace.already_posted([body], "will-revise", "AB-9", "AB-50")
        assert not impact_trace.already_posted([body], "will-revise", "AB-8")
        assert "Will retire: AB-6" in body

    def test_snapshot_round_trip_keeps_text_exactly(self):
        body = impact_trace.snapshot("AB-9", "Old title", "line 1\n|a|b|\n{code}", "aaaa1111", "bbbb2222")
        snap = impact_trace.parse_snapshot(body)
        assert snap["old_description"] == "line 1\n|a|b|\n{code}"
        assert snap["new_hash"] == "bbbb2222"
        assert impact_trace.latest_snapshot(["noise", body], "AB-9") == snap
        assert impact_trace.latest_snapshot([body], "AB-8") is None

    def test_every_kind_has_a_parseable_head(self):
        for body in (impact_trace.result("AB-9", "https://x/pull/1", {"AB-3": "passed"}),
                     impact_trace.merged("AB-9", "https://x/pull/1", ["AB-3"]),
                     impact_trace.restored("AB-9", None, ["AB-3"], ["AB-4"])):
            assert impact_trace.parse(body)["change"] == "AB-9"


def test_settings_defaults_are_off_and_shadow():
    s = impact_settings({})
    assert s["enabled"] is False and s["shadow_mode"] is True
    assert impact_settings({"labels": {"check": "x"}})["labels"]["proposed"] == "impact-proposed"
    # The shipped config equals the defaults apart from the on/off switch,
    # which a project sets for itself (see the comment in config.yaml).
    shipped = impact_settings()
    assert {k: v for k, v in shipped.items() if k != "enabled"} == \
        {k: v for k, v in DEFAULTS.items() if k != "enabled"}
    assert shipped["shadow_mode"] is True, "never ship live mode by accident"


# ─────────────────────────────────────────────────────────────────
# C1 - Agent 1 never picks up a story still under impact analysis
# ─────────────────────────────────────────────────────────────────
def test_agent1_skips_impact_labels_even_with_ai_ready(monkeypatch):
    from agents.agent1_analyst import load_agent_config
    fake = seed_jira()
    for key, extra in (("SBX-5", "impact-check"), ("SBX-6", "impact-proposed"), ("SBX-7", None)):
        fake.add("Story", f"story {key}", key=key, labels=["ai-ready"] + ([extra] if extra else []))
    jira = jira_client_over(fake, monkeypatch)
    selection = dict(load_agent_config()["selection"])
    selection.pop("sprint", None)
    found = {s["key"] for s in jira.find_stories_to_process(selection)}
    assert "SBX-7" in found and not {"SBX-5", "SBX-6"} & found


# ─────────────────────────────────────────────────────────────────
# C2 - hand-over, end to end
# ─────────────────────────────────────────────────────────────────
@pytest.fixture
def world(monkeypatch):
    fake = seed_jira()
    fake.add("Story", "Remember-me replaces the session cookie", key="SBX-5",
             labels=["impact-proposed"], components=["Login"])
    return fake, jira_client_over(fake, monkeypatch)


def _impacts_from(fake, story):
    return sorted(o for t, i, o in fake.links.values() if t == "Impacts" and i == story)


class TestHandover:
    def test_links_trace_retire_and_labels(self, world):
        fake, jira = world
        r = handover(jira, "SBX-5", {"SBX-11": "approve", "SBX-13": "retire", "SBX-21": "reject"},
                     review_key="SBX-90")
        assert r.approved == ["SBX-11"] and r.retired == ["SBX-13"] and r.rejected == ["SBX-21"]
        assert _impacts_from(fake, "SBX-5") == ["SBX-1", "SBX-11", "SBX-13"]   # tests + owner
        assert "ai-retired" in fake.issues["SBX-13"]["labels"]
        labels = fake.issues["SBX-5"]["labels"]
        assert "ai-ready" in labels and not [l for l in labels if l.startswith("impact-")]
        trace = [c for c in fake.comments["SBX-1"] if c.startswith(impact_trace.TRACE)]
        assert len(trace) == 1 and "Will revise: SBX-11" in trace[0] and "SBX-90" in trace[0]
        assert "SBX-2" not in fake.comments                                    # rejected owner untouched
        # what the next agents will see
        assert [c["key"] for c in jira.get_impacted_test_cases("SBX-5")] == ["SBX-11"]
        assert {c["key"]: c["retired"] for c in
                jira.get_impacted_test_cases("SBX-5", include_retired=True)} == \
            {"SBX-11": False, "SBX-13": True}
        assert jira.get_parent_story_key("SBX-11") == "SBX-1"                  # ownership unchanged

    def test_running_it_again_writes_nothing_new(self, world):
        fake, jira = world
        decisions = {"SBX-11": "approve"}
        handover(jira, "SBX-5", decisions, review_key="SBX-90")
        links, comments = dict(fake.links), {k: list(v) for k, v in fake.comments.items()}
        handover(jira, "SBX-5", decisions, review_key="SBX-90")
        assert fake.links == links and fake.comments == comments

    def test_all_rejected_still_makes_the_story_ready(self, world):
        fake, jira = world
        handover(jira, "SBX-5", {"SBX-11": "reject"})
        assert _impacts_from(fake, "SBX-5") == [] and "ai-ready" in fake.issues["SBX-5"]["labels"]

    @pytest.mark.parametrize("decisions,why", [
        ({"SBX-11": "?"}, "undecided"),
        ({"SBX-5": "approve"}, "cannot impact itself"),
    ])
    def test_refusals_write_nothing(self, world, decisions, why):
        fake, jira = world
        before = (dict(fake.links), list(fake.issues["SBX-5"]["labels"]))
        with pytest.raises(HandoverRefused, match=why):
            handover(jira, "SBX-5", decisions)
        assert (dict(fake.links), list(fake.issues["SBX-5"]["labels"])) == before

    def test_a_story_cannot_hand_over_its_own_test_cases(self, world):
        _fake, jira = world
        with pytest.raises(HandoverRefused, match="owns SBX-11"):
            handover(jira, "SBX-1", {"SBX-11": "approve"})

    def test_dry_run_reports_owners_and_writes_nothing(self, world):
        fake, jira = world
        links = dict(fake.links)
        r = handover(jira, "SBX-5", {"SBX-11": "approve", "SBX-21": "approve"}, dry_run=True)
        assert r.owners == {"SBX-1": ["SBX-11"], "SBX-2": ["SBX-21"]} and fake.links == links


class TestReviewDrivenHandover:
    def _review(self, fake, jira, status, decision_for_21="?"):
        rows = [{"key": "SBX-11", "owner": "SBX-1", "tier": "must-update", "score": 0.9},
                {"key": "SBX-21", "owner": "SBX-2", "tier": "review", "score": 0.4,
                 "decision": decision_for_21}]
        key = jira.create_subtask("SBX-5", "Impact Review: SBX-5",
                                  impact_review.render("SBX-5", rows))
        fake.issues[key]["status"] = status
        return key

    def test_open_review_is_not_handed_over(self, world):
        fake, jira = world
        self._review(fake, jira, "In Review", "reject")
        with pytest.raises(HandoverRefused, match="not 'Done'"):
            decisions_from_review(jira, "SBX-5")

    def test_done_review_with_an_undecided_row_is_refused(self, world):
        fake, jira = world
        self._review(fake, jira, "Done")
        key, decisions = decisions_from_review(jira, "SBX-5")
        with pytest.raises(HandoverRefused, match="SBX-21"):
            handover(jira, "SBX-5", decisions, review_key=key)

    def test_cli_from_a_done_review(self, world, monkeypatch, capsys):
        fake, jira = world
        review = self._review(fake, jira, "Done", "reject")
        import integrations.tracker as tr
        monkeypatch.setattr(tr, "get_tracker", lambda *a, **k: jira)
        from scripts.impact_handover import main
        assert main(["--story", "SBX-5", "--from-review"]) == 0
        assert _impacts_from(fake, "SBX-5") == ["SBX-1", "SBX-11"]
        assert review in fake.comments["SBX-1"][0]
        assert "revise : SBX-11" in capsys.readouterr().out

    def test_cli_refusal_exit_code(self, world, monkeypatch):
        _fake, jira = world
        import integrations.tracker as tr
        monkeypatch.setattr(tr, "get_tracker", lambda *a, **k: jira)
        from scripts.impact_handover import main
        assert main(["--story", "SBX-5", "--approve", "SBX-11", "--retire", "SBX-11"]) == 2


# Agent 3 review of #130 (fourth run)
def test_parse_rows_maps_a_full_row_and_survives_a_pipe_in_evidence():
    row = "|AB-3|AB-1|must-update|0.9|uses the error banner|retire|"
    assert impact_review.parse_rows(row)["AB-3"] == {
        "owner": "AB-1", "tier": "must-update", "score": "0.9",
        "evidence": "uses the error banner", "decision": "retire"}
    # a reviewer types a pipe in the evidence: the decision is still the LAST cell
    edited = "|AB-3|AB-1|must-update|0.9|before | after|reject|"
    assert impact_review.parse_rows(edited)["AB-3"]["decision"] == "reject"
    assert impact_review.parse(edited) == {"AB-3": "reject"}


def test_an_unknown_trace_kind_is_refused_even_under_python_O():
    with pytest.raises(ValueError, match="unknown trace kind"):
        impact_trace._head("deleted", "AB-9", None)
