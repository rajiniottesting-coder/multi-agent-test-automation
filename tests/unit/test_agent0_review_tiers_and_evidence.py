"""Agent 0's Impact Review rows: the model's verdict caps a test's tier, and
each row carries one readable evidence line - why the test is affected - while
the data keeps every structural path.

Found in the Agent 0 validation stories (October 2026).
"""

from types import SimpleNamespace
from core import impact_analysis as ia


WEIGHTS = {"structural": 0.45, "component": 0.15, "semantic": 0.15, "adjudicated": 0.25}
THRESHOLDS = {"must_update": 0.6, "review": 0.3}


def _cand(cid, structural=1.0, component=1.0, semantic=0.5):
    return SimpleNamespace(id=cid, ref=cid, test_case_key=cid, file="f", title=cid, owner="O",
                           layer=1, structural=structural, component=component,
                           semantic=semantic, paths=[], blocked_by=[])


def _tier(candidate, verdict, signals=("structural", "component", "semantic", "adjudicated")):
    judged = {candidate.id: (verdict, "r", [])} if verdict else {}
    return ia.rank([candidate], judged, WEIGHTS, THRESHOLDS, signals)[0]


def test_a_review_verdict_is_never_raised_to_must_update():
    row = _tier(_cand("C1"), "review")
    assert row["score"] >= THRESHOLDS["must_update"]          # structure alone would say so
    assert row["tier"] == "review"


def test_the_score_can_still_lower_a_judged_tier():
    weak = _cand("C2", structural=0.0, component=0.0, semantic=1.0)
    row = _tier(weak, "must-update")
    assert row["score"] == 0.4 and row["tier"] == "review"


def test_unjudged_candidates_keep_the_score_tier():
    row = _tier(_cand("C3"), None, signals=("structural", "component"))
    assert row["tier"] == "must-update"


def test_must_update_and_unaffected_verdicts_behave_as_before():
    assert _tier(_cand("C4"), "must-update")["tier"] == "must-update"
    assert _tier(_cand("C5"), "unaffected")["tier"] == "unaffected"


ROW = {"reason": "Sets a value the change removes, so the step fails.",
       "evidence": ("element p:a <- P.m <- scenario; element p:a <- P.n <- Then step; "
                    "element q:b <- Q.k <- scenario")}


def test_short_evidence_is_the_reason_and_the_elements():
    from agents.agent0_impact import short_evidence
    text = short_evidence(ROW)
    assert text == "Sets a value the change removes, so the step fails. - Elements: p:a, q:b"


def test_short_evidence_without_a_reason_names_the_elements():
    from agents.agent0_impact import short_evidence
    assert short_evidence({"reason": "", "evidence": ROW["evidence"]}) == "Elements: p:a, q:b"
    long = short_evidence({"reason": "word " * 200, "evidence": ""})
    assert len(long) <= 240 and long.endswith("...")


def test_short_evidence_names_every_changed_thing_a_row_reaches():
    """A row reached through an element AND a method names both; a shared-base
    method and a removed page (the review-tier paths of a code change) are named."""
    from agents.agent0_impact import short_evidence
    both = ("element p:a (selector `#a`) <- P.m <- Then step (assertion) <- scenario; "
            "method P.check <- step definition <- scenario")
    assert short_evidence({"reason": "", "evidence": both}) == "Elements: p:a - Methods: P.check"
    weak = "shared method Base.wait <- page method <- scenario; page q <- scenario"
    assert short_evidence({"reason": "", "evidence": weak}) == "Shared methods: Base.wait - Pages: q"
    only = "method P.check <- step definition <- scenario"
    assert short_evidence({"reason": "Why.", "evidence": only}) == "Why. - Methods: P.check"


def test_the_review_table_carries_the_short_line_and_the_data_keeps_the_paths():
    from agents.agent0_impact import _review_rows
    report = {"ranked": [dict(ROW, key="AB-1", ref="AB-1", owner="AB-9", tier="review",
                              score=0.5, blocked_by=[])]}
    row = _review_rows(report)[0]
    assert row["evidence"].startswith("Sets a value") and "<-" not in row["evidence"]
    assert "<-" in report["ranked"][0]["evidence"]
