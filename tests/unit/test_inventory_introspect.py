"""Unit tests for backlog 3.1 pure introspection logic (no browser).

Covers selector ranking, element naming, repeated-family collapsing, draft page
assembly, and the staleness diff — all on plain DOM descriptors.
"""
import pytest
from pathlib import Path

from inventory_tools.introspect import (
    _is_fragile_path,
    verify_entry_against_page,
    diff_page,
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
    is_unstable_strategy,
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
    """A BUTTON with readable text still ranks by role+name."""
    sel, strat = rank_selector("button", {}, text="Continue Shopping")
    assert strat == "role" and "button" in sel


def test_an_anchor_without_href_is_not_a_link():
    """CORRECTED 2 Aug 2026. `_IMPLICIT_ROLE` maps <a> to `link`, but ARIA only
    does so when the anchor HAS an href - without one it is `generic`. Emitting
    role=link[name='...'] for a hrefless anchor produces a locator that can
    never match, which is exactly how a checkout control styled as a button
    shipped as role=link and resolved to zero against the live app."""
    sel, strat = rank_selector("a", {"class": "btn"}, text="Proceed To Checkout")
    assert "role=link" not in sel
    assert sel == "text=Proceed To Checkout"


def test_an_anchor_prefers_its_href_over_its_name():
    """The destination is immune to the markup INSIDE the link; an accessible
    name is not. An icon font rendering from ligature text turned 'Products'
    into 'card_travel Products' and the role locator matched nothing."""
    sel, strat = rank_selector("a", {"href": "/products"}, text="card_travel Products")
    assert sel == "a[href='/products']" and strat == "href"


def test_a_record_href_becomes_a_prefix_match():
    """One anchor per record is a family, not an address."""
    sel, strat = rank_selector("a", {"href": "/product_details/1"}, text="View Product")
    assert sel == "a[href^='/product_details/']" and strat == "href-prefix"


@pytest.mark.parametrize("href", ["javascript:void(0)", "mailto:a@b.c", "tel:123"])
def test_protocol_hrefs_fall_through(href):
    """A protocol href is not a locator - rank by name instead."""
    sel, strat = rank_selector("a", {"href": href}, text="Top")
    assert strat == "role" and "link" in sel


def test_a_fragment_href_IS_used():
    """CORRECTED 4 Aug 2026. Fragment hrefs were excluded, so a collapsible
    accordion header (`href="#Women"`) fell through to role=link[name='Women']
    - and its fa-plus icon child poisoned the accessible name, so the locator
    matched ZERO. The fragment is exact, stable, and immune to icon markup."""
    sel, strat = rank_selector("a", {"href": "#Women"}, text="Women")
    assert sel == "a[href='#Women']" and strat == "href"


def test_an_icon_child_blocks_accessible_name_locators():
    """A CSS ::before glyph is folded into the accessible name but is invisible
    to textContent and innerText. Proven in a browser: a button whose DOM text
    is exactly "Add to cart" matched ZERO via role=button[name='Add to cart'].
    Any element with an icon descendant must avoid the a11y tree entirely."""
    sel, strat = rank_selector("button", {"class": "cart"}, text="Add to cart",
                               css_path="div.p button.cart", has_icon_child=True)
    assert "role=" not in sel
    assert sel == "div.p button.cart"


def test_no_icon_child_still_ranks_by_role():
    sel, strat = rank_selector("button", {}, text="Sign in", has_icon_child=False)
    assert sel == "role=button[name='Sign in']" and strat == "role"


def test_capture_records_whether_an_element_has_an_icon_child():
    js = _capture_js()
    assert "hasIconChild" in js
    assert "el.querySelector(" in js, "must look at DESCENDANTS, not the element itself"


# ── custom widgets: ARIA role / tabindex / contenteditable ────

def test_rank_custom_widget_by_role():
    sel, strat = rank_selector("div", {"role": "combobox", "aria-label": "Country"})
    assert sel == "role=combobox[name='Country']" and strat == "role"


def test_role_selector_is_stable():
    _, strat = rank_selector("div", {"role": "switch", "aria-label": "Dark mode"})
    assert not is_unstable_strategy(strat)


def test_unstable_flag_on_bare_css():
    _, strat = rank_selector("div", {})
    assert strat == "css" and is_unstable_strategy(strat)


def test_element_kind_from_role():
    assert element_kind("div", {"role": "combobox"}) == "dropdown"
    assert element_kind("div", {"role": "switch"}) == "toggle"
    assert element_kind("div", {"role": "slider"}) == "slider"


def test_build_captures_custom_widgets():
    descriptors = [
        {"tag": "div", "attrs": {"role": "combobox", "aria-label": "Country"}, "text": ""},
        {"tag": "div", "attrs": {"tabindex": "0"}, "text": "Toggle"},
        {"tag": "span", "attrs": {"contenteditable": "true"}, "text": ""},
        {"tag": "div", "attrs": {}, "text": "just text noise"},   # skipped
        {"tag": "input", "attrs": {"data-test": "email"}, "text": ""},
    ]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    assert page["elements"]["country_dropdown"] == "role=combobox[name='Country']"
    assert len(page["elements"]) == 4          # noise div skipped, 4 widgets kept
    assert "_unstable_selectors" in page       # tabindex/contenteditable had weak hooks


def test_build_no_unstable_key_when_all_stable():
    descriptors = [{"tag": "input", "attrs": {"data-test": "email"}, "text": ""}]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    assert "_unstable_selectors" not in page


# ── iframes ───────────────────────────────────────────────────

def test_build_iframe_element_gets_frame_prefix():
    descriptors = [
        {"tag": "input", "attrs": {"data-test": "card-number"}, "text": "",
         "frame": "iframe#checkout"},
    ]
    page = build_page_entry("https://x.com/pay", "Pay", descriptors, "https://x.com")
    assert page["elements"]["card_number_input"] == \
        "iframe#checkout >>> [data-test='card-number']"


def test_diff_recognizes_framed_test_id_not_new():
    inv = {"card": "iframe#checkout >>> [data-test='card-number']"}
    live = {"iframe#checkout >>> [data-test='card-number']": 1}
    out = diff_page("pay", inv, live, {"card-number"})
    assert out["new_data_tests"] == []
    assert out["missing"] == []


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
    page = build_page_entry("https://shop.example.com/", "Example Shop", descriptors,
                            "https://shop.example.com")
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


def test_nameless_interactive_role_still_uses_role():
    # a jQuery-UI slider handle: role=slider, no name -> role=slider, not bare tag
    sel, strat = rank_selector("span", {"role": "slider"})
    assert sel == "role=slider" and strat == "role"
    assert not is_unstable_strategy(strat)


def test_stable_id_div_is_captured():
    # a drag-drop target (#draggable) is a plain div with only a stable id
    descriptors = [{"tag": "div", "attrs": {"id": "draggable"}, "text": "Drag me"}]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    assert "#draggable" in page["elements"].values()


def test_generated_id_div_not_captured():
    # a framework-generated id on a plain div is noise -> skipped
    descriptors = [{"tag": "div", "attrs": {"id": "radix-42"}, "text": ""}]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    assert page["elements"] == {}


def test_pages_missing_notes():
    inv = {"pages": {
        "login": {"elements_notes": {"a": "b"}},
        "cart": {"elements": {}},           # no notes
        "menu": {"elements_notes": {}},     # empty notes
    }}
    assert set(pages_missing_notes(inv)) == {"cart", "menu"}

# ── Playwright locator coverage: label / alt / title ──────────

def test_label_locator_preferred_over_generated_id():
    """getByLabel is Playwright's recommended handle for form controls, and
    must beat a framework-generated id."""
    sel, strat = rank_selector("input", {"id": ":r0:"}, label="Email address")
    assert sel == "label=Email address" and strat == "label"


def test_label_beats_even_a_stable_id():
    """CONTRACT CHANGED: user-facing locators outrank css.

    This asserted the reverse - that a human-authored `#email-field` beat
    getByLabel("Email"). Defensible on stability grounds, but it is the
    opposite of Playwright's own guidance, and it meant that on any app whose
    forms carry ids (which is most of them) the crawler emitted css for every
    field and generated page objects read like 2015-era Selenium.

    `#id` is page.locator() css, not a getBy* method. It still ranks above
    text= and the raw css path - a deliberate id IS an author's contract - but
    it is no longer the first thing reached for.
    """
    sel, strat = rank_selector("input", {"id": "email-field"}, label="Email")
    assert sel == "label=Email" and strat == "label"


def test_id_is_used_when_nothing_user_facing_exists():
    """The css tier is a fallback, not a deletion: an element with no role,
    label, placeholder, alt or title still gets its id."""
    sel, strat = rank_selector("div", {"id": "draggable"})
    assert sel == "#draggable" and strat == "id"


def test_role_beats_id_for_a_named_control():
    """getByRole is Playwright's first recommendation, so a button with both
    an id and readable text is addressed by role."""
    sel, strat = rank_selector("button", {"id": "submit-btn"}, text="Sign in")
    assert sel == "role=button[name='Sign in']" and strat == "role"


def test_placeholder_beats_id():
    """getByPlaceholder is user-facing; #id is not."""
    sel, strat = rank_selector("input", {"id": "zip-code", "placeholder": "Zip"})
    assert strat == "placeholder"


def test_alt_locator_for_image_inputs():
    """getByAltText — image buttons carry no text node."""
    sel, strat = rank_selector("input", {"type": "image", "alt": "Search"})
    assert sel == "alt=Search" and strat == "alt"


def test_title_locator_for_iconless_control():
    """getByTitle — tooltip-only controls such as an icon 'X' close button."""
    sel, strat = rank_selector("button", {"title": "Close dialog"})
    assert sel == "title=Close dialog" and strat == "title"


def test_named_role_still_outranks_label():
    """getByRole with an accessible name stays Playwright's first choice."""
    sel, strat = rank_selector("div", {"role": "combobox", "aria-label": "Country"},
                               label="Country selector")
    assert strat == "role" and sel.startswith("role=combobox")


def test_nameless_role_ranks_below_title():
    """A nameless role is churn-proof but weaker than any named handle."""
    sel, strat = rank_selector("button", {"role": "button", "title": "Close"})
    assert sel == "title=Close" and strat == "title"


def test_new_strategies_are_all_stable():
    for strategy in ("label", "alt", "title"):
        assert not is_unstable_strategy(strategy)


def test_label_threaded_from_descriptor():
    """build_page_entry must pass the collector's `label` through."""
    descriptors = [{"tag": "input", "attrs": {"id": ":r7:"}, "text": "",
                    "label": "Full name"}]
    page = build_page_entry("https://x.com/f", "F", descriptors, "https://x.com")
    assert "label=Full name" in page["elements"].values()


# ── Ambiguous selectors (Playwright strict-mode violations) ───

def test_duplicate_selector_flagged_at_generate_time():
    """Two elements ranking to the SAME selector => strict-mode violation."""
    descriptors = [
        {"tag": "input", "attrs": {"type": "text"}, "text": ""},
        {"tag": "input", "attrs": {"type": "text"}, "text": ""},
    ]
    page = build_page_entry("https://x.com/f", "F", descriptors, "https://x.com")
    amb = page["_ambiguous_selectors"]["selectors"]
    assert "input[type='text']" in amb
    assert len(amb["input[type='text']"]) == 2


def test_no_ambiguous_key_when_all_selectors_distinct():
    descriptors = [
        {"tag": "input", "attrs": {"data-test": "a"}, "text": ""},
        {"tag": "input", "attrs": {"data-test": "b"}, "text": ""},
    ]
    page = build_page_entry("https://x.com/f", "F", descriptors, "https://x.com")
    assert "_ambiguous_selectors" not in page


def test_diff_page_reports_live_multi_match():
    """A selector matching several elements must be drift, not silence."""
    out = diff_page("home", {"box": "input[type='text']"},
                    {"input[type='text']": 4}, set())
    assert out["ambiguous"] == [
        {"element": "box", "selector": "input[type='text']", "matches": 4}]
    assert out["missing"] == []          # it resolves, so it is not stale


def test_single_match_is_not_ambiguous():
    out = diff_page("home", {"box": "[data-test='x']"},
                    {"[data-test='x']": 1}, set())
    assert out["ambiguous"] == []


def test_summarize_drift_counts_ambiguous_as_drift():
    diff = diff_page("home", {"box": "input"}, {"input": 3}, set())
    rep = summarize_drift({"home": diff}, [])
    assert rep["ambiguous_selectors"] == 1
    assert rep["has_drift"] is True


# ── Concrete last-resort fallback (no ambiguous tag selectors) ─

def test_css_path_used_when_nothing_semantic_available():
    """A bare tag is a CATEGORY, not a locator. The structural path must win."""
    sel, strat = rank_selector("input", {"type": "text"},
                               css_path="body > input:nth-of-type(2)")
    assert sel == "body > input:nth-of-type(2)" and strat == "css"


def test_semantic_handles_still_beat_css_path():
    """The concrete path is a LAST resort — never preferred over a real handle."""
    for attrs, label, expected_start in (
        ({"data-test": "user"}, "", "[data-test="),
        ({"id": "email-field"}, "", "#email-field"),
        ({"role": "combobox", "aria-label": "Country"}, "", "role=combobox"),
        ({"id": ":r0:"}, "Email", "label=Email"),
    ):
        sel, _ = rank_selector("input", attrs, label=label,
                               css_path="body > input:nth-of-type(9)")
        assert sel.startswith(expected_start), sel


def test_css_path_still_reported_unstable():
    """Concrete but layout-brittle — the reviewer must still be warned."""
    _, strat = rank_selector("div", {}, css_path="body > div:nth-of-type(3)")
    assert is_unstable_strategy(strat)


def test_css_path_prevents_duplicate_selectors():
    """Two otherwise-identical inputs must not collide into one selector."""
    descriptors = [
        {"tag": "input", "attrs": {"type": "text"}, "text": "",
         "cssPath": "body > input:nth-of-type(1)"},
        {"tag": "input", "attrs": {"type": "text"}, "text": "",
         "cssPath": "body > input:nth-of-type(2)"},
    ]
    page = build_page_entry("https://x.com/f", "F", descriptors, "https://x.com")
    assert len(set(page["elements"].values())) == 2
    assert "_ambiguous_selectors" not in page


def test_falls_back_to_tag_when_no_css_path_supplied():
    """Callers that pass no cssPath (unit tests, older data) still work."""
    sel, strat = rank_selector("div", {})
    assert sel == "div" and strat == "css"


# ── Volatile (runtime-data) text ──────────────────────────────

def test_static_text_stays_stable():
    for label in ("Submit", "Add to cart", "Sign in"):
        _, strat = rank_selector("button", {}, label)
        assert not is_unstable_strategy(strat), label


def test_volatile_text_is_flagged_not_rejected():
    """Still used (may be the only handle) but reported for review."""
    for label in ("Welcome back, John Smith", "3 items in cart",
                  "Total: $49.99", "Updated 2 minutes ago"):
        sel, strat = rank_selector("button", {}, label)
        assert label[:20] in sel, "the name must still be used"
        assert is_unstable_strategy(strat), label


def test_volatile_names_reach_unstable_selectors_block():
    descriptors = [{"tag": "button", "attrs": {}, "text": "3 items in cart"}]
    page = build_page_entry("https://x.com/c", "C", descriptors, "https://x.com")
    assert page["_unstable_selectors"]["elements"]


def test_stable_handle_still_wins_over_volatile_text():
    sel, strat = rank_selector("button", {"data-test": "cart"}, "3 items in cart")
    assert sel == "[data-test='cart']" and not is_unstable_strategy(strat)


# ── Dynamic ATTRIBUTE values -> starts-with anchoring ─────────

def test_dynamic_attr_value_uses_starts_with():
    """A record/session id inside the value must not be matched exactly."""
    sel, strat = rank_selector("div", {"data-test": "user-profile-8891"})
    assert sel == "[data-test^='user-profile-']" and strat == "data-test-prefix"


def test_hex_and_date_segments_also_anchored():
    assert rank_selector("div", {"data-test": "session-a3f8b21c"})[0] \
        == "[data-test^='session-']"
    assert rank_selector("div", {"id": "order-row-20260725"})[0] \
        == "[id^='order-row-']"


def test_fully_static_attr_value_matched_exactly():
    """Nothing dynamic in the value -> exact match, no needless loosening."""
    sel, strat = rank_selector("div", {"data-test": "add-to-cart"})
    assert sel == "[data-test='add-to-cart']" and strat == "data-test"


def test_framework_id_prefix_is_not_anchored():
    """radix-/ember- match every element the library renders — useless."""
    sel, _ = rank_selector("div", {"id": "radix-123", "name": "menu"})
    assert sel == "div[name='menu']"


def test_prefix_strategies_count_as_stable():
    for strategy in ("data-test-prefix", "id-prefix"):
        assert not is_unstable_strategy(strategy)


# ── Dynamic TEXT -> prefer a stable handle over a churning name ─

def test_stable_attribute_beats_volatile_accessible_name():
    """'3 items in cart' churns; the title does not — the title must win."""
    sel, strat = rank_selector("button", {"title": "Open cart"}, "3 items in cart")
    assert sel == "title=Open cart" and strat == "title"


def test_volatile_name_used_only_when_nothing_stable_exists():
    sel, strat = rank_selector("button", {}, "3 items in cart")
    assert "3 items in cart" in sel and strat == "role-volatile"
    assert is_unstable_strategy(strat)

# ── Duplicate semantic selectors -> nth disambiguation ────────

def test_duplicate_semantic_selectors_get_nth_suffix():
    """Three links reading 'Canada' each rank to the SAME valid locator.
    Playwright is strict, so all three would fail without disambiguation."""
    # TWO members: still disambiguated by index. Three or more is a repeated
    # WIDGET and collapses into a family instead - see the test below.
    descriptors = [
        {"tag": "a", "attrs": {"href": "/canada"}, "text": "Canada"},
        {"tag": "a", "attrs": {"href": "/canada"}, "text": "Canada"},
    ]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    sels = list(page["elements"].values())
    assert sels == [
        "a[href='/canada'] >> nth=0",
        "a[href='/canada'] >> nth=1",
    ]


def test_three_or_more_repeats_collapse_into_one_family():
    """CHANGED 5 Aug 2026. A repeated widget produced one key per instance:
    68 named add_cart_link, add_cart_link_2, add_cart_link_3 ... A test cannot
    know which index is a given product, every key costs prompt tokens on every
    generated file, and nothing declared the family a validator should protect.

    They share a base selector here, so the family key IS that base and the
    collapse loses nothing."""
    descriptors = [
        {"tag": "a", "attrs": {"href": "/canada"}, "text": "Canada"},
        {"tag": "a", "attrs": {"href": "/canada"}, "text": "Canada"},
        {"tag": "a", "attrs": {"href": "/canada"}, "text": "Canada"},
    ]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    assert list(page["elements"]) == ["canada_links"]
    assert page["elements"]["canada_links"] == "a[href='/canada']"
    assert page["multi_match"] == ["canada_links"]
    assert page.get("multi_match_note"), "a declared family needs its note"


def test_a_family_with_no_shared_selector_is_reported():
    """When every instance fell back to its own structural path there is no
    locator that matches the family, so inventing one would be a lie. One is
    kept as a representative and the gap is surfaced for a human to close."""
    # Hidden, so each falls to its OWN css path - there is no shared handle.
    # Identical visible text would collapse to `text=Buy` and share a base,
    # which is the case the branch above already covers.
    descriptors = [
        {"tag": "a", "attrs": {}, "text": "Buy", "visible": False,
         "cssPath": f"body > div:nth-of-type({i}) > a"}
        for i in range(4)
    ]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    gap = page.get("_families_without_a_shared_handle", {})
    assert gap.get("elements"), "a family with no shared handle must be reported"
    assert "data-test" in gap["warning"], "the warning must say how to fix it"


def test_unique_selector_gets_no_suffix():
    """Only duplicates are indexed - a unique locator stays clean."""
    descriptors = [{"tag": "a", "attrs": {"href": "/mexico"}, "text": "Mexico"}]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    assert list(page["elements"].values()) == ["a[href='/mexico']"]


def test_collision_still_reported_after_disambiguation():
    """The selectors now work, but the reviewer must still be told - the real
    fix is a data-test attribute in the app."""
    descriptors = [
        {"tag": "a", "attrs": {"href": "/canada"}, "text": "Canada"},
        {"tag": "a", "attrs": {"href": "/canada"}, "text": "Canada"},
    ]
    page = build_page_entry("https://x.com/", "X", descriptors, "https://x.com")
    assert "a[href='/canada']" in page["_ambiguous_selectors"]["selectors"]


# ─────────────────────────────────────────────────────────────────────────
# multi_match emission
#
# The generator already knew which entries stood for a FAMILY of elements,
# but only said so in `_ambiguous_selectors` / `family_members_seen` — draft
# aids that are stripped during curation. Agent 2 therefore read an inventory
# with the classification removed, and SCRUM-104 clicked a selector matching
# three dropdown options. This is now a first-class field that survives.
# ─────────────────────────────────────────────────────────────────────────

def test_collapsed_family_is_reported_as_multi_match():
    descs = [
        {"tag": "button", "attrs": {"data-test": "buy-item-backpack"}, "text": "Buy"},
        {"tag": "button", "attrs": {"data-test": "buy-item-bikelight"}, "text": "Buy"},
        {"tag": "input", "attrs": {"data-test": "search"}, "text": ""},
    ]
    entry = build_page_entry("https://x.test/items", "Items", descs, "https://x.test")
    assert entry["multi_match"], "the collapsed family must be declared"
    fam = entry["multi_match"][0]
    assert "^=" in entry["elements"][fam], "a prefix selector is a family by construction"
    assert "search_input" not in entry["multi_match"], "a singleton is not a family"


def test_multi_match_is_present_even_when_empty():
    """A stable key means curation cannot silently drop the concept."""
    entry = build_page_entry("https://x.test/p", "P",
                             [{"tag": "input", "attrs": {"data-test": "only"}, "text": ""}],
                             "https://x.test")
    assert entry["multi_match"] == []
    assert "multi_match_note" in entry


def test_multi_match_is_not_a_draft_only_field():
    """`_`-prefixed fields get stripped at curation; this one must not be."""
    entry = build_page_entry("https://x.test/p", "P", [], "https://x.test")
    assert not any(k.startswith("_") for k in ("multi_match", "multi_match_note"))
    assert "multi_match" in entry


def test_disambiguated_duplicates_are_not_families():
    """Two links reading the same thing get `>> nth=N` and each resolves to
    one element — accidental duplication, not an intentional family."""
    descs = [
        {"tag": "a", "attrs": {}, "text": "Canada"},
        {"tag": "a", "attrs": {}, "text": "Canada"},
    ]
    entry = build_page_entry("https://x.test/p", "P", descs, "https://x.test")
    assert entry["multi_match"] == []
    assert any(">> nth=" in s for s in entry["elements"].values())


def test_numeric_members_are_pinned_not_collapsed():
    """buy-item-101 / -202 anchor to the same prefix, so each is disambiguated
    with  and resolves to ONE element. Pinned duplicates are not a
    family - only a key that stands for the whole set is."""
    descs = [
        {"tag": "button", "attrs": {"data-test": "buy-item-101"}, "text": "Buy"},
        {"tag": "button", "attrs": {"data-test": "buy-item-202"}, "text": "Buy"},
    ]
    entry = build_page_entry("https://x.test/i", "I", descs, "https://x.test")
    assert entry["multi_match"] == []
    assert all(">> nth=" in s for s in entry["elements"].values())

# ─────────────────────────────────────────────────────────────────────────
# The tools must honour the inventory's own declarations
#
# A clean sweep still printed ten "problems": every declared multi_match family
# reported as AMBIG, and every declared conditional key as STALE. The operator
# then has to remember which ten are fine, which is exactly how a real finding
# gets missed. A declaration that the tooling ignores is not a declaration.
# ─────────────────────────────────────────────────────────────────────────

def test_a_declared_family_is_not_reported_as_drift():
    """Matching several elements IS the multi_match declaration being
    satisfied. The generation-time validator already stops anyone clicking it."""
    out = diff_page(
        "products",
        {"cards": ".card", "heading": "h1"},
        {".card": 34, "h1": 1},
        set(),
        declared_family={"cards"},
    )
    assert out["ambiguous"] == []


def test_an_undeclared_family_is_still_reported():
    """The check must keep its teeth: a selector matching many elements that
    NOBODY declared is the failure this was built to catch."""
    out = diff_page(
        "products",
        {"cards": ".card"},
        {".card": 34},
        set(),
        declared_family=set(),
    )
    assert len(out["ambiguous"]) == 1
    assert out["ambiguous"][0]["matches"] == 34


def test_a_declared_conditional_key_is_not_reported_missing():
    """It exists only after an interaction, and this tool never clicks."""
    out = diff_page(
        "login",
        {"error": "text=Wrong password", "heading": "h1"},
        {"text=Wrong password": 0, "h1": 1},
        set(),
        declared_conditional={"error"},
    )
    names = [m.get("element") if isinstance(m, dict) else m for m in out["missing"]]
    assert "error" not in names


def test_an_undeclared_zero_match_is_still_reported():
    out = diff_page("login", {"error": "text=Wrong password"},
                    {"text=Wrong password": 0}, set(), declared_conditional=set())
    names = [m.get("element") if isinstance(m, dict) else m for m in out["missing"]]
    assert "error" in names


def test_declarations_default_to_empty():
    """Called without the new arguments, behaviour is unchanged - so any other
    caller keeps working."""
    out = diff_page("p", {"c": ".card"}, {".card": 5}, set())
    assert len(out["ambiguous"]) == 1


# ─────────────────────────────────────────────────────────────────────────
# Hidden elements have no accessible role
#
# The browser measures `visible` during capture, and the value was recorded and
# then discarded. Every collapsed accordion link, closed-modal button and
# inactive carousel slide therefore shipped with a role= selector - and the
# ACCESSIBILITY TREE excludes hidden nodes, so those resolve to zero for as
# long as the element stays hidden. That produced ~40 STALE lines in one sweep,
# indistinguishable from genuinely broken selectors.
#
# Proven 4 Aug 2026 in a real browser: a display:none link matched 0 via
# role=link[name='WOMEN'] and 1 via a[href='#women'] on the same node.
# ─────────────────────────────────────────────────────────────────────────

def test_a_hidden_element_does_not_get_a_role_selector():
    sel, strat = rank_selector("a", {"href": "#Women"}, text="WOMEN", visible=False)
    assert "role=" not in sel
    assert sel == "a[href='#Women']"


def test_a_hidden_element_falls_back_to_a_css_path():
    """When it has no id, name or href, the structural path is the only handle
    that still resolves while the element is hidden."""
    sel, strat = rank_selector("button", {"class": "close"}, text="Continue Shopping",
                               css_path="div.modal button.close", visible=False)
    assert sel == "div.modal button.close"
    assert strat == "css-path-hidden"


def test_a_hidden_element_still_prefers_a_real_id():
    sel, strat = rank_selector("div", {"id": "checkout-panel"}, visible=False)
    assert sel == "#checkout-panel" and strat == "id-hidden"


def test_visibility_defaults_to_true_so_existing_callers_are_unaffected():
    a, _ = rank_selector("button", {}, text="Sign in")
    b, _ = rank_selector("button", {}, text="Sign in", visible=True)
    assert a == b == "role=button[name='Sign in']"


def test_a_visible_element_is_unchanged():
    """The fix must not weaken the ranking for anything actually on screen."""
    sel, strat = rank_selector("button", {"class": "cart"}, text="Add to cart", visible=True)
    assert sel == "role=button[name='Add to cart']" and strat == "role"


def test_hidden_elements_are_auto_declared_conditional():
    """A hidden element is interaction-gated by definition. Declaring it in the
    draft means verify_locators reads it as COND (expected) instead of adding
    it to a wall of STALE lines a human then has to triage by hand."""
    descs = [
        {"tag": "a", "attrs": {"href": "/products"}, "text": "Products", "visible": True},
        {"tag": "a", "attrs": {"href": "#Women"}, "text": "WOMEN", "visible": False,
         "cssPath": "div.panel a"},
    ]
    e = build_page_entry("https://x.test/p", "P", descs, "https://x.test")
    assert e["conditional"] == ["women_link"]
    assert "products_link" not in e["conditional"]
    assert "conditional_note" in e


def test_a_page_with_nothing_hidden_declares_no_conditional():
    descs = [{"tag": "a", "attrs": {"href": "/products"}, "text": "Products", "visible": True}]
    e = build_page_entry("https://x.test/p", "P", descs, "https://x.test")
    assert "conditional" not in e


# ─────────────────────────────────────────────────────────────────────────
# The capture script's two content rules
#
# These live in JS inside inventory_tools/browser.py, so they cannot be called
# from Python. Asserting on the source is weaker than executing it, but it does
# stop a future edit quietly dropping a rule that each cost a full sweep to
# find.
# ─────────────────────────────────────────────────────────────────────────

def _capture_js() -> str:
    return (Path(__file__).resolve().parents[2]
            / "inventory_tools" / "browser.py").read_text(encoding="utf-8")


def test_capture_reads_textContent_not_innerText_for_matching():
    """innerText returns the RENDERED text, with CSS text-transform applied. A
    link styled `text-transform: uppercase` reads "WOMEN" while the DOM says
    "Women", and Playwright computes the accessible name from the raw text -
    so a role locator built from innerText resolves to ZERO. Proven in a real
    browser: same node, 0 matches via the rendered casing, 2 via the raw."""
    js = _capture_js()
    assert "text: (el.textContent" in js, "matching text must come from textContent"
    assert "renderedText: (el.innerText" in js, "keep innerText separately, for naming"


def test_capture_skips_hidden_form_tokens():
    """A CSRF token's value is regenerated on every request; one crawl produced an
    element named after the nonce itself."""
    assert "el.type === 'hidden'" in _capture_js()


def test_capture_flags_third_party_content_without_dropping_it():
    """Ad networks rotate their link text per impression, so every captured ad
    link is stale by the next page load. But the container list is a HEURISTIC
    about the web in general - it can miss a network, or catch a real element
    in a similarly-named div - so the draft flags them for a human to delete
    rather than deciding on a guess."""
    js = _capture_js()
    assert "adsbygoogle" in js
    assert "el.closest(" in js, "must match by ANCESTOR, not just the element itself"
    assert "thirdParty," in js, "the flag must reach the descriptor"
    assert "if (el.closest('.adsbygoogle" not in js, "must FLAG, not silently skip"


def test_third_party_elements_are_surfaced_for_review():
    descs = [
        {"tag": "a", "attrs": {"href": "/products"}, "text": "Products", "visible": True},
        {"tag": "a", "attrs": {"href": "/x"}, "text": "Winter Wear",
         "visible": True, "thirdParty": True},
    ]
    e = build_page_entry("https://x.test/p", "P", descs, "https://x.test")
    # kept, so nothing is lost on a bad guess...
    assert "winter_wear_link" in e["elements"]
    # ...but flagged, so a human deletes it deliberately
    assert e["_third_party_elements"]["elements"] == ["winter_wear_link"]
    assert "DELETE" in e["_third_party_elements"]["warning"]


def test_a_page_with_no_embeds_has_no_review_block():
    descs = [{"tag": "a", "attrs": {"href": "/p"}, "text": "P", "visible": True}]
    e = build_page_entry("https://x.test/p", "P", descs, "https://x.test")
    assert "_third_party_elements" not in e


# ─────────────────────────────────────────────────────────────────────────
# The crawler MEASURES its selectors instead of predicting them
#
# Ranking has to guess what Playwright will do: what the accessible name
# resolves to, what the a11y tree contains. Four separate bug classes came from
# wrong guesses - CSS text-transform, ::before icon glyphs, hidden elements,
# hrefless anchors - and each was found only when a human ran a sweep days
# later. The page is still open when the entry is built, so the guess can be
# replaced with a measurement.
# ─────────────────────────────────────────────────────────────────────────

class _FakeLoc:
    def __init__(self, n): self._n = n
    def count(self): return self._n


class _FakePage:
    """Answers with real counts for real selectors, zero for anything else."""
    def __init__(self, truth): self.truth = truth
    def locator(self, sel): return _FakeLoc(self.truth.get(sel, 0))
    def get_by_label(self, t): return _FakeLoc(0)
    def get_by_placeholder(self, t): return _FakeLoc(0)
    def get_by_alt_text(self, t): return _FakeLoc(0)
    def get_by_title(self, t): return _FakeLoc(0)


def test_a_selector_that_matches_nothing_is_recorded_not_shipped_silently():
    page = _FakePage({"a[href='#S']": 1})
    entry = {"elements": {"good": "a[href='#S']",
                          "bad": "role=link[name='S']"}}
    out = verify_entry_against_page(page, entry)
    names = [u["element"] for u in out["_unresolved_selectors"]["elements"]]
    assert names == ["bad"]
    assert "DELETE" not in out["_unresolved_selectors"]["warning"], \
        "the element exists - only the locator is wrong, so do not tell anyone to delete it"


def test_the_element_is_kept_so_the_fix_is_visible():
    """Dropping it would hide the problem; the draft must still show it."""
    page = _FakePage({})
    out = verify_entry_against_page(page, {"elements": {"bad": "role=link[name='X']"}})
    assert "bad" in out["elements"]


def test_a_family_is_declared_from_measurement_not_guesswork():
    page = _FakePage({".card": 34, "#one": 1})
    out = verify_entry_against_page(page, {"elements": {"cards": ".card", "one": "#one"}})
    assert out["multi_match"] == ["cards"]
    assert "MEASURED" in out["multi_match_note"]


def test_measured_families_merge_with_any_already_declared():
    page = _FakePage({".card": 34, ".row": 5})
    out = verify_entry_against_page(
        page, {"elements": {"cards": ".card", "rows": ".row"},
               "multi_match": ["rows"]})
    assert out["multi_match"] == ["cards", "rows"]


def test_a_clean_page_gains_no_unresolved_block():
    page = _FakePage({"#a": 1, "#b": 1})
    out = verify_entry_against_page(page, {"elements": {"a": "#a", "b": "#b"}})
    assert "_unresolved_selectors" not in out


def test_a_broken_selector_engine_is_recorded_not_fatal():
    """A malformed selector must not abort the whole crawl."""
    class Boom(_FakePage):
        def locator(self, sel): raise ValueError("unknown engine")
    out = verify_entry_against_page(Boom({}), {"elements": {"x": "bogus=1"}})
    assert out["_unresolved_selectors"]["elements"][0]["matches"] == -1


def test_an_empty_page_entry_is_returned_untouched():
    assert verify_entry_against_page(_FakePage({}), {"elements": {}}) == {"elements": {}}


# ─────────────────────────────────────────────────────────────────────────
# Structural css paths are not handles
#
# `div:nth-of-type(14) > div > p > div` describes where an element SAT during
# one crawl. Ad slots and lazy content shift sibling indices between loads, so
# it breaks silently the moment anything above it renders differently. Nine of
# these reached a draft and read as ordinary elements.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("selector", [
    "body > section:nth-of-type(2) > div > div > div > p > div",
    "#aswift_1_host > div > div > div:nth-of-type(3)",
    "div > div > div > div > div > div > span",
])
def test_deep_structural_paths_are_fragile(selector):
    assert _is_fragile_path(selector)


@pytest.mark.parametrize("selector", [
    "#login-form",                 # a bare id IS a handle
    "a[href='/products']",
    "role=button[name='Save']",
    "label=Email",
    "div.panel button.cart",       # short, class-based
    "#cart_info tbody tr",         # real curated selector - must stay clean
    ".product-image-wrapper",
])
def test_real_handles_are_not_flagged(selector):
    assert not _is_fragile_path(selector)


def test_an_id_with_descendants_is_still_a_path():
    """`#host > div:nth-of-type(3)` merely STARTS at a handle - the descendants
    still encode sibling position, which is the fragile part."""
    assert _is_fragile_path("#host > div > div:nth-of-type(3)")
    assert not _is_fragile_path("#host")


def test_fragile_selectors_are_surfaced_even_when_they_resolve():
    """They match today. Surfacing them while the page is open beats a mystery
    STALE line after the next layout shift."""
    page = _FakePage({"body > div > div > div > div > div > div > p": 1})
    out = verify_entry_against_page(
        page, {"elements": {"x": "body > div > div > div > div > div > div > p"}})
    assert out["_fragile_selectors"]["elements"][0]["element"] == "x"
    assert "_unresolved_selectors" not in out, "it resolves - it is fragile, not broken"


def test_capture_carries_third_party_across_shadow_boundaries():
    """el.closest() stops at a shadow root, so an element inside an ad frame's
    shadow DOM cannot see the ad host above it. Eight selectors rooted at an ad
    iframe host reached a draft as ordinary elements because of this."""
    js = _capture_js()
    assert "inheritedThirdParty" in js
    assert "walk(el.shadowRoot, hostIsThirdParty)" in js
    assert "walk(document, false)" in js