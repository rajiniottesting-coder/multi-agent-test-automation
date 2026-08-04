"""Tests for scripts/promote_draft.py — merging and pruning crawl drafts.

The tool exists because acting on the crawler's review blocks by hand, across
five pages and 500 elements, is tedious and easy to get half-right — and a
half-pruned draft is worse than an unpruned one, because the leftovers look
deliberate.
"""
import json
from pathlib import Path

import pytest

from scripts.promote_draft import merge_drafts, prune, _named_elements


def _draft(pages: dict) -> dict:
    return {"app_name": "X", "base_url": "https://x.test", "pages": pages}


def _write(tmp_path: Path, name: str, pages: dict) -> Path:
    p = tmp_path / f"{name}.draft.json"
    p.write_text(json.dumps(_draft(pages)), encoding="utf-8")
    return p


# ── review-block parsing ────────────────────────────────────────────────

def test_named_elements_reads_both_block_shapes():
    """_third_party_elements uses plain strings; _fragile_selectors uses dicts."""
    assert _named_elements({"elements": ["a", "b"]}) == {"a", "b"}
    assert _named_elements({"elements": [{"element": "a", "selector": "#a"}]}) == {"a"}
    assert _named_elements(None) == set()
    assert _named_elements({}) == set()


# ── pruning ─────────────────────────────────────────────────────────────

def test_only_third_party_elements_are_removed_by_default():
    """A "fragile" flag means the ELEMENT IS REAL and only its handle is poor.
    Verified against a live draft: add_cart_button, continue_shopping_button and
    continue_cart_button were all flagged fragile, and a cart story needs all
    three. Deleting a real element because its locator is weak loses work;
    improving the locator does not."""
    inv = _draft({"home": {
        "elements": {"real": "#real", "ad": "#ad", "path": "body > div > p"},
        "_third_party_elements": {"elements": ["ad"]},
        "_fragile_selectors": {"elements": [{"element": "path", "selector": "body > div > p"}]},
        "_unstable_selectors": {"elements": ["real"]},
    }})
    prune(inv)
    page = inv["pages"]["home"]
    assert set(page["elements"]) == {"real", "path"}, "only the ad may be dropped"
    assert page["_selectors_to_improve"]["elements"] == ["path"]
    assert "_third_party_elements" not in page
    assert "_unstable_selectors" not in page


def test_drop_fragile_is_opt_in():
    inv = _draft({"home": {
        "elements": {"real": "#real", "path": "body > div > p"},
        "_fragile_selectors": {"elements": [{"element": "path"}]},
    }})
    prune(inv, drop_fragile=True)
    assert set(inv["pages"]["home"]["elements"]) == {"real"}


def test_the_improve_list_only_names_elements_that_survived():
    """If a fragile element is ALSO third-party it is deleted, and must not
    then appear in a TODO list for an element that no longer exists."""
    inv = _draft({"home": {
        "elements": {"ad": "#aswift > div"},
        "_third_party_elements": {"elements": ["ad"]},
        "_fragile_selectors": {"elements": [{"element": "ad"}]},
    }})
    prune(inv)
    page = inv["pages"]["home"]
    assert page["elements"] == {}
    assert "_selectors_to_improve" not in page


def test_unstable_elements_are_kept():
    """_unstable_selectors is a QUALITY warning, not a delete list — those
    selectors resolve. Removing them would gut a page that merely lacks
    data-test attributes."""
    inv = _draft({"home": {
        "elements": {"a": ".a", "b": ".b"},
        "_unstable_selectors": {"elements": ["a", "b"]},
    }})
    prune(inv)
    assert set(inv["pages"]["home"]["elements"]) == {"a", "b"}


def test_fragile_paths_stay_by_default():
    inv = _draft({"home": {
        "elements": {"real": "#real", "path": "body > div > p"},
        "_fragile_selectors": {"elements": [{"element": "path"}]},
    }})
    prune(inv)
    assert "path" in inv["pages"]["home"]["elements"]


def test_declarations_naming_a_removed_element_are_repaired():
    """A multi_match list pointing at a deleted key would fail the framework's
    own consistency check the moment it was committed."""
    inv = _draft({"products": {
        "elements": {"cards": ".card", "ad": "#ad"},
        "multi_match": ["cards", "ad"],
        "conditional": ["ad"],
        "conditional_note": "...",
        "_third_party_elements": {"elements": ["ad"]},
    }})
    prune(inv)
    page = inv["pages"]["products"]
    assert page["multi_match"] == ["cards"]
    assert "conditional" not in page, "emptied lists are dropped, not left as []"
    assert "conditional_note" not in page


def test_a_page_with_nothing_flagged_is_untouched():
    inv = _draft({"home": {"elements": {"a": "#a"}}})
    report = prune(inv)
    assert report == [("home", 0, 1, 0)]


# ── merging ─────────────────────────────────────────────────────────────

def test_distinct_pages_merge_straight_through(tmp_path):
    a = _write(tmp_path, "one", {"login": {"elements": {"x": "#x"}}})
    b = _write(tmp_path, "two", {"cart": {"elements": {"y": "#y"}}})
    merged, collisions = merge_drafts([a, b])
    assert set(merged["pages"]) == {"login", "cart"}
    assert collisions == {}


def test_a_page_captured_twice_is_kept_separately(tmp_path):
    """Two crawls of one path in different auth states are NOT duplicates — the
    nav differs, and on some apps the whole page does. Silently keeping one
    would discard a real difference."""
    a = _write(tmp_path, "anon", {"home": {"elements": {"signup": "#signup"}}})
    b = _write(tmp_path, "auth", {"home": {"elements": {"logout": "#logout"}}})
    merged, collisions = merge_drafts([a, b])
    assert set(merged["pages"]) == {"home__anon", "home__auth"}
    assert "home" not in merged["pages"], "neither version may be privileged"
    assert collisions == {"home": ["anon", "auth"]}


def test_both_versions_survive_a_collision(tmp_path):
    a = _write(tmp_path, "anon", {"home": {"elements": {"signup": "#signup"}}})
    b = _write(tmp_path, "auth", {"home": {"elements": {"logout": "#logout"}}})
    merged, _ = merge_drafts([a, b])
    assert merged["pages"]["home__anon"]["elements"] == {"signup": "#signup"}
    assert merged["pages"]["home__auth"]["elements"] == {"logout": "#logout"}


def test_top_level_metadata_is_carried_from_the_first_draft(tmp_path):
    a = _write(tmp_path, "one", {"login": {"elements": {}}})
    b = _write(tmp_path, "two", {"cart": {"elements": {}}})
    merged, _ = merge_drafts([a, b])
    assert merged["app_name"] == "X"
    assert merged["base_url"] == "https://x.test"


def test_merging_a_single_draft_is_a_no_op(tmp_path):
    a = _write(tmp_path, "only", {"home": {"elements": {"x": "#x"}}})
    merged, collisions = merge_drafts([a])
    assert set(merged["pages"]) == {"home"}
    assert collisions == {}