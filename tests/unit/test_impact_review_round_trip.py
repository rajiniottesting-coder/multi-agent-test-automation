"""The Impact Review table must read back after the tracker's round trip.

A tracker that stores rich text can return an issue key it auto-linked as a
link instead of plain text, and a link's own "|" is not a cell boundary. If
the parser missed those rows, a Done review would hand over with no
decisions: the story labelled ai-ready and no test revised. These tests pin
every key form and the refusal for a row whose key cannot be read.

Generic keys only; no network.
"""
import pytest

from core import impact_review
from core.impact_handover import HandoverRefused, decisions_from_review

BASE = "https://tracker.example"

HEADER = "||Test case||Owner||Tier||Score||Evidence||Decision||"


def _row(key_cell, owner_cell="AB-1", decision="approve"):
    return f"|{key_cell}|{owner_cell}|review|0.56|element p:k <- Page.m <- scenario|{decision}|"


KEY_FORMS = {
    "plain": "AB-12",
    "titled link": f"[AB-12|{BASE}/browse/AB-12]",
    "smart link": f"[{BASE}/browse/AB-12#icft=AB-12|{BASE}/browse/AB-12#icft=AB-12|smart-link]",
    "bare url": f"{BASE}/browse/AB-12#icft=AB-12",
}


@pytest.mark.parametrize("form", KEY_FORMS)
def test_every_key_form_reads_back(form):
    owner = KEY_FORMS[form].replace("AB-12", "AB-1")
    text = "\n".join([HEADER, _row(KEY_FORMS[form], owner, "approve"),
                      _row("AB-13", "AB-1", " *reject* ")])
    assert impact_review.parse(text) == {"AB-12": "approve", "AB-13": "reject"}
    rows = impact_review.parse_rows(text)
    assert rows["AB-12"]["owner"] == "AB-1"
    assert rows["AB-12"]["tier"] == "review" and rows["AB-12"]["decision"] == "approve"
    assert impact_review.unreadable_rows(text) == []


def test_render_then_parse_round_trips():
    rows = [{"key": "AB-12", "owner": "AB-1", "tier": "must-update", "score": 0.9, "evidence": "e"},
            {"key": "AB-13", "owner": "AB-1", "tier": "review", "score": 0.5, "evidence": "a|b"}]
    assert impact_review.parse(impact_review.render("AB-9", rows)) == {"AB-12": "approve",
                                                                       "AB-13": "?"}


def test_unknown_words_stay_undecided():
    assert impact_review.parse("\n".join([HEADER, _row("AB-12", decision="maybe")])) == {"AB-12": "?"}


class _Tracker:
    def __init__(self, description, status="Done"):
        self.sub = [{"key": "AB-50", "summary": "Impact Review: AB-9",
                     "status": status, "description": description}]

    def get_subtasks(self, key):
        return self.sub


def test_a_row_without_a_readable_key_refuses_the_hand_over():
    text = "\n".join([HEADER, _row("AB-12"), _row("a test case")])
    with pytest.raises(HandoverRefused, match="cannot read"):
        decisions_from_review(_Tracker(text), "AB-9")


def test_a_table_with_no_rows_refuses_the_hand_over():
    with pytest.raises(HandoverRefused, match="no decision rows"):
        decisions_from_review(_Tracker("Impact Review for AB-9.\n\n" + HEADER), "AB-9")


def test_a_linked_table_hands_over_its_decisions():
    text = "\n".join([HEADER, _row(KEY_FORMS["smart link"], decision="approve")])
    assert decisions_from_review(_Tracker(text), "AB-9") == ("AB-50", {"AB-12": "approve"})
