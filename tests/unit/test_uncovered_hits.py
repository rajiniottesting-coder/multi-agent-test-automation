"""uncovered_hits: which uncovered element names a story names in full.

Conservative on purpose: a missed hint is safe, a false one costs reviewer time.
"""

from core import impact_analysis as ia

UNCOVERED = {"checkout": {"promo_banner": "x", "cancel_button": "y"}}


def test_every_word_of_the_name_must_appear():
    assert ia.uncovered_hits("Add a promo banner to checkout", UNCOVERED) == \
        [("checkout", "promo_banner")]


def test_one_word_of_a_two_word_name_is_not_enough():
    assert ia.uncovered_hits("The button now says yes", UNCOVERED) == []


def test_matching_ignores_case():
    assert ia.uncovered_hits("PROMO BANNER shown", UNCOVERED) == [("checkout", "promo_banner")]


def test_plurals_do_not_match():
    assert ia.uncovered_hits("two promo banners", UNCOVERED) == []


def test_a_name_with_no_word_of_four_letters_is_never_matched():
    assert ia.uncovered_hits("an OK up on it", {"p": {"ok_up": "x"}}) == []


def test_empty_or_missing_uncovered_gives_no_hits():
    assert ia.uncovered_hits("promo banner", {}) == []
    assert ia.uncovered_hits("promo banner", None) == []
    assert ia.uncovered_hits("", UNCOVERED) == []


def test_hits_are_sorted_by_page_then_element():
    uncovered = {"b": {"x_text": "1"}, "a": {"zeta_link": "2", "alpha_link": "3"}}
    text = "x text zeta link alpha link"
    assert ia.uncovered_hits(text, uncovered) == [("a", "alpha_link"), ("a", "zeta_link"), ("b", "x_text")]


def test_with_uncovered_hint_adds_pages_without_touching_the_input():
    seeds = ia.Seeds(pages={"login"})
    out, hits = ia.with_uncovered_hint(seeds, "promo banner", UNCOVERED)
    assert out.pages == {"login", "checkout"} and hits == [("checkout", "promo_banner")]
    assert seeds.pages == {"login"}


def test_the_page_seed_scores_below_must_update_and_above_review():
    """A hint alone must land in the review band. Checked against the weights
    the rest of Agent 0 uses, not restated here."""
    assert 0.3 <= ia.PAGE_ONLY < 0.6
