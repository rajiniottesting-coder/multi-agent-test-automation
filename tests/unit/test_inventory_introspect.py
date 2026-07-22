"""Unit tests for backlog 3.1 pure introspection logic (no browser).

Covers selector ranking, element naming, repeated-family collapsing, draft page
assembly, and the staleness diff — all on plain DOM descriptors.
"""
from inventory_tools.introspect import (
    rank_selector,
    derive_element_name,
    element_kind,
    collapse_repeated_families,
    build_page_entry,
    guess_page_object,
    url_to_path,
    diff_page,
    summarize_drift,
    pages_missing_notes,
    _looks_generated_id,
)


# ── selector ranking ──────────────────────────────────────────

def test_rank_prefers_data_test():
    sel, strat = rank_selector("input", {"data-test": "username", "id": "u1"})
    assert sel == "[data-test='username']" and strat == "data-test"


def test_rank_falls_to_stable_id():
    sel, strat = rank_selector("button", {"id": "react-burger-menu-btn"})
    assert sel == "#react-burger-menu-btn" and strat == "id"


def test_rank_skips_generated_id():
    sel, strat = rank_selector("div", {"id": "radix-123", "name": "menu"})
    assert strat != "id"  # generated id rejected
    assert sel == "div[name='menu']"


def test_rank_name_then_aria_then_placeholder():
    assert rank_selector("input", {"name": "email"})[0] == "input[name='email']"
    assert rank_selector("input", {"aria-label": "Search"})[0] == "input[aria-label='Search']"
    assert rank_selector("input", {"placeholder": "Zip"})[0] == "input[placeholder='Zip']"


def test_rank_role_text_fallback():
    sel, strat = rank_selector("a", {}, text="Continue Shopping")
    assert strat == "role+text" and "link" in sel


def test_generated_id_detection():
    assert _looks_generated_id("radix-42")
    assert _looks_generated_id("ember1234")
    assert _looks_generated_id("x1234567")
    assert not _looks_generated_id("login-button")
    assert not _looks_generated_id("react-burger-menu-btn")


# ── naming + kind ─────────────────────────────────────────────

def test_derive_name_from_data_test():
    assert derive_element_name("button", {"data-test": "login-button"}) == "login_button"


def test_derive_name_camelcase_split():
    assert derive_element_name("input", {"data-test": "firstName"}) == "first_name_input"


def test_derive_name_avoids_double_suffix():
    # base already ends in the kind -> no "login_button_button"
    assert derive_element_name("button", {"data-test": "login-button"}) == "login_button"


def test_element_kind_by_input_type():
    assert element_kind("input", {"type": "submit"}) == "button"
    assert element_kind("input", {"type": "password"}) == "input"
    assert element_kind("select", {}) == "dropdown"
    assert element_kind("a", {}) == "link"


# ── family collapsing ─────────────────────────────────────────

def test_collapse_repeated_family():
    els = {
        "add_to_cart_backpack_button": {"selector": "[data-test='add-to-cart-backpack']"},
        "add_to_cart_bike_light_button": {"selector": "[data-test='add-to-cart-bike-light']"},
        "login_button": {"selector": "[data-test='login-button']"},
    }
    out = collapse_repeated_families(els)
    assert any(v["selector"] == "[data-test^='add-to-cart-']" for v in out.values())
    assert "login_button" in out  # unrelated element preserved


def test_collapse_leaves_singletons_alone():
    els = {"add_to_cart_backpack_button": {"selector": "[data-test='add-to-cart-backpack']"}}
    out = collapse_repeated_families(els)
    assert "add_to_cart_backpack_button" in out  # single member -> not collapsed


# ── page assembly ─────────────────────────────────────────────

def test_url_to_path():
    assert url_to_path("https://x.com/inventory.html", "https://x.com") == "/inventory.html"
    assert url_to_path("https://x.com/") == "/"
    assert url_to_path("https://x.com/item?id=4") == "/item?id=4"


def test_guess_page_object():
    pof, poc = guess_page_object("/checkout-step-one.html")
    assert pof == "pages/checkout_step_one_page.py"
    assert poc == "CheckoutStepOnePage"


def test_build_page_entry_shape_and_stubs():
    descriptors = [
        {"tag": "input", "attrs": {"data-test": "username"}, "text": ""},
        {"tag": "input", "attrs": {"data-test": "password", "type": "password"}, "text": ""},
        {"tag": "input", "attrs": {"data-test": "login-button", "type": "submit"}, "text": "Login"},
        {"tag": "div", "attrs": {}, "text": "ignore me"},  # non-interactable, untagged -> skipped
    ]
    page = build_page_entry("https://www.saucedemo.com/", "Swag Labs", descriptors,
                            "https://www.saucedemo.com")
    assert page["url"] == "/"
    assert page["elements"]["username_input"] == "[data-test='username']"
    assert page["elements"]["login_button"] == "[data-test='login-button']"
    assert "ignore" not in str(page["elements"])  # noise skipped
    # human-only stubs present so the gap is visible
    assert page["elements_notes"] == {} and page["key_methods"] == [] and page["errors"] == {}
    assert page["components"] == []
    assert "AUTO-GENERATED DRAFT" in page["implementation_status"]


def test_build_page_entry_dedupes_names():
    descriptors = [
        {"tag": "a", "attrs": {}, "text": "Home"},
        {"tag": "a", "attrs": {}, "text": "Home"},
    ]
    page = build_page_entry("https://x.com/p", "P", descriptors, "https://x.com")
    names = list(page["elements"])
    assert len(names) == len(set(names))  # no duplicate keys


# ── staleness diff ────────────────────────────────────────────

def test_diff_page_flags_missing_selector():
    inv = {"login_button": "[data-test='login-button']", "user": "[data-test='username']"}
    live_resolved = {"[data-test='login-button']": 0, "[data-test='username']": 1}
    out = diff_page("login", inv, live_resolved, {"username"})
    assert out["missing"] == [{"element": "login_button", "selector": "[data-test='login-button']"}]


def test_diff_page_flags_new_data_test():
    inv = {"user": "[data-test='username']"}
    live_resolved = {"[data-test='username']": 1}
    out = diff_page("login", inv, live_resolved, {"username", "new-widget"})
    assert out["new_data_tests"] == ["new-widget"]


def test_diff_page_prefix_selector_covers_family():
    inv = {"add_buttons": "[data-test^='add-to-cart-']"}
    live_resolved = {"[data-test^='add-to-cart-']": 6}
    live = {"add-to-cart-backpack", "add-to-cart-bike-light"}
    out = diff_page("inv", inv, live_resolved, live)
    assert out["new_data_tests"] == []  # family members covered by prefix


def test_summarize_drift_flags():
    per_page = {
        "login": {"missing": [{"element": "x", "selector": "[data-test='x']"}], "new_data_tests": []},
        "cart": {"missing": [], "new_data_tests": ["new-thing"]},
    }
    rpt = summarize_drift(per_page, missing_pages=["ghost"])
    assert rpt["has_drift"] is True
    assert rpt["stale_selectors"] == 1
    assert rpt["new_untracked_data_tests"] == 1
    assert rpt["unreachable_pages"] == ["ghost"]


def test_summarize_no_drift():
    per_page = {"login": {"missing": [], "new_data_tests": []}}
    rpt = summarize_drift(per_page, missing_pages=[])
    assert rpt["has_drift"] is False


# ── app-agnostic: custom test-id attributes ──────────────────

def test_rank_selector_custom_attr_data_cy():
    # An app that tags with data-cy (Cypress) — ranker must prefer it.
    sel, strat = rank_selector("button", {"data-cy": "submit", "id": "x"},
                               test_attrs=("data-cy", "data-test"))
    assert sel == "[data-cy='submit']" and strat == "data-cy"


def test_data_cy_in_default_set():
    # data-cy ships in the default set, so no config needed for Cypress apps.
    sel, _ = rank_selector("button", {"data-cy": "submit"})
    assert sel == "[data-cy='submit']"


def test_build_page_entry_with_custom_attrs():
    descriptors = [
        {"tag": "div", "attrs": {"data-cy": "menu-toggle"}, "text": ""},  # tagged div captured
        {"tag": "input", "attrs": {"data-cy": "search"}, "text": ""},
    ]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com",
                            test_attrs=("data-cy",))
    assert page["elements"]["menu_toggle_element"] == "[data-cy='menu-toggle']"
    assert page["elements"]["search_input"] == "[data-cy='search']"


def test_family_collapse_custom_attr_preserves_attribute():
    els = {
        "buy_item_101_button": {"selector": "[data-cy='buy-item-101']"},
        "buy_item_202_button": {"selector": "[data-cy='buy-item-202']"},
    }
    out = collapse_repeated_families(els, test_attrs=("data-cy",))
    assert any(v["selector"] == "[data-cy^='buy-item-']" for v in out.values())


def test_diff_page_custom_attr():
    inv = {"search": "[data-cy='search']"}
    live_resolved = {"[data-cy='search']": 1}
    out = diff_page("home", inv, live_resolved, {"search", "new-cy-widget"},
                    test_attrs=("data-cy",))
    assert out["new_data_tests"] == ["new-cy-widget"]


def test_pages_missing_notes():
    inv = {"pages": {
        "login": {"elements_notes": {"a": "b"}},
        "cart": {"elements": {}},           # no notes
        "menu": {"elements_notes": {}},     # empty notes
    }}
    assert set(pages_missing_notes(inv)) == {"cart", "menu"}