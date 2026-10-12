"""Two things a person reading an Agent 0 report must not miss.

1. An affected scenario with no test case cannot be a row in the Impact
   Review (rows are decided and handed over by test case key), so it used to
   vanish from the review. It is now listed under "Revise by hand", with the
   reason: a reserved file the agents never edit, or a missing marker.
2. The embedded JSON is the agents' copy of the report. A note above it says
   so, outside the code block, so reading it back is unchanged.

Generic keys and paths only; no network, no model.
"""
import agents.agent0_impact as a0
from core import impact_analysis as ia
from core import impact_review


def _row(ref, key, file, tier="review", score=0.56):
    return {"id": "C1", "ref": ref, "key": key, "file": file, "title": ref, "owner": key and "AB-1",
            "layer": 1, "score": score, "tier": tier, "reason": "r", "evidence": "e",
            "blocked_by": []}


def _report(*ranked):
    return {"change_ref": "AB-9", "content_hash": "h", "graph_sha": "g", "ranked": list(ranked),
            "by_owner": {}, "unaffected": [], "not_judged": [], "no_component": False,
            "seeds": {"elements": [], "methods": [], "pages": [], "dropped": []},
            "dropped_assessments": []}


MARKED = _row("AB-12", "AB-12", "features/a.feature")
RESERVED = _row("features/base.feature::Reserved one", None, "features/base.feature")
UNMARKED = _row("features/b.feature::Unmarked one", None, "features/b.feature", "must-update", 0.9)


def test_unmarked_affected_scenarios_are_listed_with_why(monkeypatch):
    monkeypatch.setattr(a0, "_reserved_paths", lambda: {"features/base.feature"})
    text = a0._render_report(_report(MARKED, RESERVED, UNMARKED), "Impact report")
    assert "Revise by hand" in text
    assert "features/base.feature::Reserved one (review, 0.56) - reserved file" in text
    assert "features/b.feature::Unmarked one (must-update, 0.9) - no test case marker" in text


def test_no_section_when_every_affected_scenario_has_a_test_case(monkeypatch):
    monkeypatch.setattr(a0, "_reserved_paths", lambda: set())
    assert "Revise by hand" not in a0._render_report(_report(MARKED), "Impact report")


def test_the_review_lists_them_and_still_parses(monkeypatch):
    monkeypatch.setattr(a0, "_reserved_paths", lambda: set())
    report = _report(MARKED, UNMARKED)
    description = (impact_review.render("AB-9", a0._review_rows(report))
                   + "\n".join(a0._manual_section(report)) + "\n\n" + ia.embed(report))
    assert "features/b.feature::Unmarked one" in description
    assert impact_review.parse(description) == {"AB-12": "?"}
    assert impact_review.unreadable_rows(description) == []
    assert ia.extract(description)["content_hash"] == "h"


def test_the_data_block_carries_a_do_not_edit_note_and_still_reads_back():
    embedded = ia.embed(_report(MARKED))
    assert embedded.startswith(ia.DATA_NOTE + "\n" + ia.REPORT_OPEN)
    assert ia.extract("prose\n\n" + embedded)["ranked"][0]["key"] == "AB-12"
