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


# ─────────────────────────────────────────────────────────────
# Generality audit (G4): the kind word, accented text, dedupe numbers
# ─────────────────────────────────────────────────────────────

KINDS = {"form": {"coupon_code_input": "a", "apply_button_2": "b",
                  "grosse_wahlen_link": "c", "search": "d"}}


def test_the_kind_word_is_not_needed_when_the_subject_has_two_words():
    """Stories say "field", "box", "Feld" - not the generator's "input"."""
    assert ia.uncovered_hits("Add a coupon code field", KINDS) == [("form", "coupon_code_input")]


def test_a_single_subject_word_still_needs_its_kind_word():
    """'apply' alone is a common verb; it must not fire on every story."""
    assert ia.uncovered_hits("apply the voucher", KINDS) == []
    assert ia.uncovered_hits("the apply button moves", KINDS) == [("form", "apply_button_2")]


def test_a_dedupe_number_is_not_needed():
    assert ia.uncovered_hits("apply button", KINDS) == [("form", "apply_button_2")]


def test_accented_story_text_matches_a_folded_name():
    assert ia.uncovered_hits("Neue Option: Größe wählen", KINDS) == [("form", "grosse_wahlen_link")]


def test_a_bare_kind_name_needs_that_word():
    assert ia.uncovered_hits("search results improve", KINDS) == [("form", "search")]


def test_the_kind_suffix_set_lives_beside_the_name_builder():
    from inventory_tools.introspect import NAME_KIND_SUFFIXES, element_kind
    for tag in ("button", "a", "select", "textarea", "input"):
        assert element_kind(tag, {}) in NAME_KIND_SUFFIXES
