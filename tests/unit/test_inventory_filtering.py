"""Unit tests for Phase-2 Tier-2 backlog 2.2 — component-wise inventory filtering.

  filter_inventory_by_components(data, components)
  AppContext.load_page_inventory_json(components)

No Jira / LLM / network. Pure dict + JSON logic driven through a temp inventory
file and a monkeypatched AppContext. Mirrors the 2.1 module-selection semantics:
core-equivalent ("always") pages are always kept, component-tagged pages are
selected by the story's Jira Components, and an unmatched/empty filter safely
falls back to the full inventory.
"""
import json

import pytest

from core.app_context import AppContext, filter_inventory_by_components


# A compact inventory covering every branch: two component groups, an "always"
# page, the small metadata blocks, and the internal _inventory_conventions note.
SAMPLE = {
    "app_name": "SampleApp",
    "base_url": "https://example.test",
    "_inventory_conventions": {"note": "internal only — must be stripped"},
    "test_users": {"std": "std_user / pw"},
    "pages": {
        "login": {"url": "/", "components": ["Login"], "elements": {"u": "#u"}},
        "cart": {"url": "/cart", "components": ["Cart"], "elements": {"c": "#c"}},
        "checkout": {"url": "/co", "components": ["Checkout"], "elements": {"f": "#f"}},
        "menu": {"url": "(overlay)", "always": True, "elements": {"m": "#m"}},
    },
    "common_errors": {"bad": "nope"},
}


def _pages(data):
    return set(data["pages"])


# ─────────────────────────────────────────────────────────────
# filter_inventory_by_components — the pure function
# ─────────────────────────────────────────────────────────────

def test_none_keeps_all_pages():
    out = filter_inventory_by_components(SAMPLE, None)
    assert _pages(out) == {"login", "cart", "checkout", "menu"}


def test_empty_list_keeps_all_pages():
    out = filter_inventory_by_components(SAMPLE, [])
    assert _pages(out) == {"login", "cart", "checkout", "menu"}


def test_single_component_selects_that_page_plus_always():
    out = filter_inventory_by_components(SAMPLE, ["Login"])
    assert _pages(out) == {"login", "menu"}  # menu is always


def test_multiple_components_union():
    out = filter_inventory_by_components(SAMPLE, ["Cart", "Checkout"])
    assert _pages(out) == {"cart", "checkout", "menu"}


def test_matching_is_case_space_hyphen_insensitive():
    # "check-out" / "CHECKOUT" / " Checkout " all normalize to the Checkout tag
    for variant in ["check out", "CHECKOUT", " Checkout ", "check-out"]:
        # our sample tags it "Checkout"; only exact-normalized should match.
        out = filter_inventory_by_components(SAMPLE, [variant])
        # "check out"/"check-out" normalize to check_out != checkout, so they
        # match nothing and fall back to all; "CHECKOUT"/" Checkout " match.
        if variant.strip().lower().replace(" ", "_").replace("-", "_") == "checkout":
            assert _pages(out) == {"checkout", "menu"}
        else:
            assert _pages(out) == {"login", "cart", "checkout", "menu"}


def test_unknown_component_injects_all_INVENTORY_PAGES():
    out = filter_inventory_by_components(SAMPLE, ["Nonexistent"])
    assert _pages(out) == {"login", "cart", "checkout", "menu"}


def test_only_always_match_falls_back_to_all():
    # A component that matches nothing but "always" pages should NOT collapse the
    # inventory to just the menu — it must fall back to the full set.
    data = {
        "pages": {
            "menu": {"always": True, "elements": {}},
            "login": {"components": ["Login"], "elements": {}},
        }
    }
    out = filter_inventory_by_components(data, ["DoesNotExist"])
    assert _pages(out) == {"menu", "login"}


def test_meta_keys_stripped_from_output():
    out = filter_inventory_by_components(SAMPLE, ["Login"])
    assert "_inventory_conventions" not in out
    for page in out["pages"].values():
        assert "components" not in page
        assert "always" not in page


def test_metadata_blocks_always_retained():
    out = filter_inventory_by_components(SAMPLE, ["Login"])
    assert out["app_name"] == "SampleApp"
    assert out["test_users"] == {"std": "std_user / pw"}
    assert out["common_errors"] == {"bad": "nope"}


def test_input_not_mutated():
    before = json.dumps(SAMPLE, sort_keys=True)
    filter_inventory_by_components(SAMPLE, ["Login"])
    assert json.dumps(SAMPLE, sort_keys=True) == before


def test_non_dict_returned_unchanged():
    assert filter_inventory_by_components("not a dict", ["Login"]) == "not a dict"


def test_inventory_without_pages_only_strips_meta():
    data = {"app_name": "X", "_inventory_conventions": {"a": 1}}
    out = filter_inventory_by_components(data, ["Login"])
    assert out == {"app_name": "X"}


# ─────────────────────────────────────────────────────────────
# AppContext.load_page_inventory_json — the integration point
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def ctx_with_inventory(tmp_path, monkeypatch):
    inv = tmp_path / "inventory.json"
    inv.write_text(json.dumps(SAMPLE), encoding="utf-8")
    ctx = AppContext(
        name="SampleApp",
        base_url="https://example.test",
        inventory_file="inventory.json",
        reference_feature="features/x.feature",
        reference_step_def="tests/step_defs/test_x.py",
        reference_page_object="pages/x_page.py",
        reserved_paths=(),
        extendable_paths=(),
    )
    monkeypatch.setattr(AppContext, "inventory_path", lambda self: inv)
    return ctx


def test_load_no_arg_is_backward_compatible(ctx_with_inventory):
    """No-arg call returns the full inventory (minified), meta stripped."""
    s = ctx_with_inventory.load_page_inventory_json()
    d = json.loads(s)
    assert _pages(d) == {"login", "cart", "checkout", "menu"}
    assert "_inventory_conventions" not in d


def test_load_filtered_by_component(ctx_with_inventory):
    s = ctx_with_inventory.load_page_inventory_json(["Cart"])
    d = json.loads(s)
    assert _pages(d) == {"cart", "menu"}


def test_load_filtered_is_smaller(ctx_with_inventory):
    full = ctx_with_inventory.load_page_inventory_json()
    one = ctx_with_inventory.load_page_inventory_json(["Login"])
    assert len(one) < len(full)


def test_load_output_is_minified(ctx_with_inventory):
    s = ctx_with_inventory.load_page_inventory_json(["Login"])
    assert ", " not in s and '": ' not in s  # compact separators


def test_load_malformed_json_falls_back_to_raw(tmp_path, monkeypatch):
    inv = tmp_path / "inventory.json"
    inv.write_text("{ this is not valid json ]", encoding="utf-8")
    ctx = AppContext(
        name="X", base_url="u", inventory_file="inventory.json",
        reference_feature="f", reference_step_def="s", reference_page_object="p",
        reserved_paths=(), extendable_paths=(),
    )
    monkeypatch.setattr(AppContext, "inventory_path", lambda self: inv)
    # Must not raise, even with a component filter — returns raw text.
    out = ctx.load_page_inventory_json(["Login"])
    assert out == "{ this is not valid json ]"


def test_load_missing_file_still_raises(tmp_path, monkeypatch):
    ctx = AppContext(
        name="X", base_url="u", inventory_file="nope.json",
        reference_feature="f", reference_step_def="s", reference_page_object="p",
        reserved_paths=(), extendable_paths=(),
    )
    monkeypatch.setattr(AppContext, "inventory_path", lambda self: tmp_path / "nope.json")
    with pytest.raises(FileNotFoundError):
        ctx.load_page_inventory_json(["Login"])

# ─────────────────────────────────────────────────────────────────────────
# Review artefacts never reach the LLM
#
# Convention: anything whose key starts with `_` is a note for a HUMAN to act
# on and delete before committing. Previously only `components` and `always`
# were stripped, so a half-curated draft sent _unstable_selectors,
# _fragile_selectors and _third_party_elements straight into the prompt —
# tokens spent on lists the model must ignore, and an invitation to treat a
# flagged element as ordinary.
# ─────────────────────────────────────────────────────────────────────────

def test_underscore_blocks_are_stripped_before_the_llm():
    inv = {"pages": {"p": {
        "components": ["X"], "always": False,
        "elements": {"a": "#a"},
        "elements_notes": {"a": "a note"},
        "key_methods": ["go()"],
        "multi_match": ["a"],
        "conditional": ["a"],
        "_unstable_selectors": {"elements": ["a"]},
        "_fragile_selectors": {"elements": []},
        "_third_party_elements": {"elements": ["ad"]},
        "_selectors_to_improve": {"elements": ["a"]},
        "_unresolved_selectors": {"elements": []},
    }}}
    out = filter_inventory_by_components(inv, ["X"])
    kept = set(out["pages"]["p"])
    assert kept == {"elements", "elements_notes", "key_methods",
                    "multi_match", "conditional"}
    assert not any(k.startswith("_") for k in kept)


def test_the_fields_agent_2_needs_still_arrive():
    """multi_match is ENFORCED by a validator and conditional is documentation
    the model acts on — stripping either would be a regression, not a cleanup."""
    inv = {"pages": {"p": {"components": ["X"], "elements": {"a": "#a"},
                           "multi_match": ["a"], "conditional": ["a"],
                           "elements_notes": {}, "key_methods": []}}}
    page = filter_inventory_by_components(inv, ["X"])["pages"]["p"]
    for field in ("elements", "multi_match", "conditional",
                  "elements_notes", "key_methods"):
        assert field in page


def test_routing_metadata_is_still_stripped():
    """components and always decide WHICH pages are sent; repeating them
    inside the payload is noise."""
    inv = {"pages": {"p": {"components": ["X"], "always": True, "elements": {}}}}
    assert set(filter_inventory_by_components(inv, ["X"])["pages"]["p"]) == {"elements"}


def test_top_level_underscore_keys_are_stripped_too():
    """A curated file carries `_VERIFICATION_STATUS` and `_inventory_conventions`
    at the top level. Both are notes to a human, and page-level stripping alone
    left them spending tokens in every generation prompt."""
    inv = {"app_name": "X", "base_url": "u",
           "_VERIFICATION_STATUS": "checked 2 Aug",
           "_inventory_conventions": {"selectors": "..."},
           "pages": {"p": {"components": ["X"], "elements": {"a": "#a"}}}}
    out = filter_inventory_by_components(inv, ["X"])
    assert not any(k.startswith("_") for k in out)
    assert out["app_name"] == "X" and "pages" in out


def test_underscore_keys_inside_elements_are_not_treated_as_selectors():
    """The tools excluded one key by NAME (`_selector_strategies`). The crawler
    has since grown several more, and each new one would have been measured as
    if it were a locator."""
    page = {"elements": {"real": "#real", "_selector_strategies": {"real": "id"},
                         "_anything_new": {"x": 1}}}
    selectors = {n: s for n, s in page["elements"].items()
                 if isinstance(s, str) and not n.startswith("_")}
    assert selectors == {"real": "#real"}