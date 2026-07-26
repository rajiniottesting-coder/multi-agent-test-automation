"""Pure inventory-introspection logic (backlog 3.1) — no Playwright, no I/O.

A DOM "descriptor" is a plain dict the Playwright layer produces per element:

    {"tag": "input", "attrs": {"data-test": "username", "type": "text", ...},
     "text": "", "visible": True}

Everything here operates on those dicts and plain data structures, so it is
fully unit-testable without a browser. The two entry points are:

    build_page_entry(url, title, descriptors, base_url)  -> a page dict (generate)
    diff_page(inventory_selectors, live_resolved, live_data_tests)  -> drift (staleness)
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


# ─────────────────────────────────────────────────────────────
# Selector ranking — most stable strategy first: prefer a dedicated
# test-id attribute, then a stable id, then name/aria/placeholder,
# then role+text, then a css fallback.
# ─────────────────────────────────────────────────────────────

# Dedicated test-id attributes, most-common conventions first. This is the ONE
# app-specific knob: apps tag elements with different attributes (React Testing
# Library uses data-testid, Cypress data-cy, Playwright data-test, etc.). The
# default set covers the common conventions so the tools work out of the box on
# most apps; override per app by passing `test_attrs=(...)` to the functions
# below, or `--test-attrs` on the CLIs. Nothing here is tied to any one app.
TEST_ID_ATTRS = (
    "data-test", "data-testid", "data-test-id", "data-qa", "data-cy",
    "data-automation-id", "data-tid",
)

# Delimiter used to express "enter this iframe, then locate" in a selector
# string: "iframe#checkout >>> [data-test='card']" (chainable for nested frames).
# The staleness checker parses this to page.frame_locator(...).locator(...).
FRAME_DELIM = ">>>"

# ids that look framework-generated and must NOT be used as selectors.
_GENERATED_ID = re.compile(
    r"(^:r[0-9a-z]+:$)"          # React useId ":r0:"
    r"|(^radix-)"                # Radix UI
    r"|(^headlessui-)"           # Headless UI
    r"|(^ember\d+$)"             # Ember
    r"|(^[0-9a-f]{8}-[0-9a-f]{4}-)"  # uuid-ish
    r"|(\d{5,})",                # long digit runs
    re.IGNORECASE,
)

_INTERACTABLE_TAGS = {"input", "button", "select", "textarea", "a"}

_IMPLICIT_ROLE = {
    "a": "link", "button": "button", "select": "combobox", "textarea": "textbox",
}

# ARIA roles that denote an interactive control. A div/span carrying one of
# these (React-Select, MUI, Ant Design, custom toggles, etc.) is captured even
# without a test-id, and gets a churn-proof role= selector rather than brittle
# css. This is what lets the tool handle complex/custom widgets in any app.
_INTERACTIVE_ROLES = {
    "button", "link", "checkbox", "radio", "switch", "combobox", "listbox",
    "option", "menuitem", "menuitemcheckbox", "menuitemradio", "tab", "textbox",
    "searchbox", "slider", "spinbutton", "treeitem", "menuitemradio", "menu",
    "menubar", "tablist", "grid", "gridcell", "row", "columnheader", "rowheader",
    "combobox", "dialog", "radiogroup",
}

# role -> the element_kind name used as a naming suffix
_ROLE_KIND = {
    "combobox": "dropdown", "listbox": "dropdown", "switch": "toggle",
    "checkbox": "checkbox", "radio": "radio", "slider": "slider",
    "spinbutton": "spinner", "searchbox": "search", "textbox": "input",
    "tab": "tab", "menuitem": "menuitem", "option": "option", "link": "link",
    "button": "button", "treeitem": "treeitem", "row": "row", "gridcell": "cell",
}


def _looks_generated_id(value: str) -> bool:
    return bool(_GENERATED_ID.search(value or ""))


def _css_escape_value(value: str) -> str:
    return value.replace("'", "\\'")


def rank_selector(tag: str, attrs: dict, text: str = "",
                  test_attrs: tuple = TEST_ID_ATTRS,
                  label: str = "") -> tuple[str, str]:
    """Return (selector, strategy) picking the most stable available handle.

    Priority, aligned with Playwright's own locator recommendations:

        test-id attr > stable id > name > role+accessible-name (getByRole)
        > label (getByLabel) > aria-label > placeholder (getByPlaceholder)
        > alt (getByAltText) > title (getByTitle) > nameless role
        > text (getByText) > css fallback

    Every strategy above the css fallback maps to a first-class Playwright
    locator, so generated page objects use the API Playwright actually
    recommends rather than brittle css. XPath is deliberately never emitted.

    `label` is the text of the element's associated <label> — a SEPARATE DOM
    element, so it must be supplied by the collector; it cannot be read from
    `attrs`. It is Playwright's recommended handle for form controls.

    The strategy label reveals how stable the pick is; a "css" strategy means
    no durable hook was found (see `is_unstable_strategy`).
    """
    a = attrs or {}
    for key in test_attrs:
        if a.get(key):
            return (f"[{key}='{_css_escape_value(a[key])}']", key)
    if a.get("id") and not _looks_generated_id(a["id"]):
        return (f"#{a['id']}", "id")
    if a.get("name"):
        return (f"{tag}[name='{_css_escape_value(a['name'])}']", "name")
    # accessible role + name — churn-proof, handles custom/div-based widgets.
    role = a.get("role") or _IMPLICIT_ROLE.get(tag)
    acc_name = (a.get("aria-label") or (text or "")).strip()
    # getByRole WITH an accessible name — Playwright's first recommendation.
    if role in _INTERACTIVE_ROLES and acc_name:
        return (f"role={role}[name='{_css_escape_value(acc_name[:40])}']", "role")
    # getByLabel — Playwright's recommended handle for form controls. Survives
    # id/class churn because it is tied to the visible label a user reads.
    lbl = (label or "").strip()
    if lbl:
        return (f"label={_css_escape_value(lbl[:60])}", "label")
    if a.get("aria-label"):
        return (f"{tag}[aria-label='{_css_escape_value(a['aria-label'])}']", "aria-label")
    if a.get("placeholder"):
        return (f"{tag}[placeholder='{_css_escape_value(a['placeholder'])}']", "placeholder")
    # getByAltText — images and image buttons carry no text node.
    if a.get("alt"):
        return (f"alt={_css_escape_value(a['alt'][:60])}", "alt")
    # getByTitle — tooltip-only controls (icon buttons, close 'X's).
    if a.get("title"):
        return (f"title={_css_escape_value(a['title'][:60])}", "title")
    if role and acc_name:  # non-interactive role but has a name (weak but usable)
        return (f"role={role}[name='{_css_escape_value(acc_name[:40])}']", "role")
    # Nameless interactive role: churn-proof, but weaker than any named handle
    # above, so it deliberately ranks below label/alt/title.
    if role in _INTERACTIVE_ROLES:
        return (f"role={role}", "role")
    if (text or "").strip() and tag in ("a", "button"):
        return (f"text={_css_escape_value(text.strip()[:40])}", "text")
    if a.get("type"):
        return (f"{tag}[type='{_css_escape_value(a['type'])}']", "css")
    return (tag, "css")


# strategies that produced a durable handle; anything else ("css") is fragile.
_STABLE_STRATEGIES = set(TEST_ID_ATTRS) | {
    "id", "name", "role", "label", "aria-label", "placeholder", "alt", "title",
    "text", "data-test-prefix",
}


def is_unstable_strategy(strategy: str) -> bool:
    """True when the only handle found is a fragile css fallback (no durable
    attribute, role, label, or text) — the reviewer should add a data-test."""
    return strategy not in _STABLE_STRATEGIES


# ─────────────────────────────────────────────────────────────
# Element naming + kind
# ─────────────────────────────────────────────────────────────

def _slug_to_name(value: str) -> str:
    """'add-to-cart-backpack' / 'firstName' -> snake_case token."""
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)  # camelCase split
    value = re.sub(r"[^0-9a-zA-Z]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_").lower()


def element_kind(tag: str, attrs: dict) -> str:
    """Semantic element kind used as a name suffix ('button', 'input', ...)."""
    a = attrs or {}
    if tag == "input":
        t = (a.get("type") or "text").lower()
        return {
            "submit": "button", "button": "button", "checkbox": "checkbox",
            "radio": "radio", "password": "input", "email": "input",
        }.get(t, "input")
    native = {
        "button": "button", "select": "dropdown", "textarea": "input",
        "a": "link",
    }.get(tag)
    if native:
        return native
    # custom widget: derive the kind from its ARIA role if it has one
    role = (a.get("role") or "").lower()
    if role in _ROLE_KIND:
        return _ROLE_KIND[role]
    return "element"


def derive_element_name(tag: str, attrs: dict, text: str = "",
                        test_attrs: tuple = TEST_ID_ATTRS) -> str:
    """Human-ish snake_case name from the strongest identifier available."""
    a = attrs or {}
    base = ""
    for key in (*test_attrs, "name", "aria-label", "placeholder"):
        if a.get(key):
            base = _slug_to_name(a[key])
            break
    if not base and a.get("id") and not _looks_generated_id(a["id"]):
        base = _slug_to_name(a["id"])
    if not base and text.strip():
        base = _slug_to_name(text.strip()[:30])
    kind = element_kind(tag, a)
    if not base:
        return kind
    # avoid doubled suffixes like "submit_button_button"
    if base.endswith(kind):
        return base
    return f"{base}_{kind}"


# ─────────────────────────────────────────────────────────────
# Repeated-family collapsing (e.g. buy-item-<slug> -> ^= selector)
# ─────────────────────────────────────────────────────────────

def _strip_frame_prefix(selector: str) -> str:
    """Return the element part of a (possibly frame-chained) selector."""
    if FRAME_DELIM in selector:
        return selector.rsplit(FRAME_DELIM, 1)[-1].strip()
    return selector


def _parse_test_attr(selector: str, test_attrs: tuple = TEST_ID_ATTRS):
    """Return (attr, value) if selector is [attr='value'] for a test-id attr.
    Handles frame-chained selectors by inspecting the element part."""
    m = re.match(r"\[([a-zA-Z-]+)='([^']+)'\]$", _strip_frame_prefix(selector))
    if m and m.group(1) in test_attrs:
        return m.group(1), m.group(2)
    return None


def _parse_test_prefix(selector: str, test_attrs: tuple = TEST_ID_ATTRS):
    """Return (attr, prefix) if selector is [attr^='prefix'] for a test-id attr."""
    m = re.match(r"\[([a-zA-Z-]+)\^='([^']+)'\]$", _strip_frame_prefix(selector))
    if m and m.group(1) in test_attrs:
        return m.group(1), m.group(2)
    return None


def _lcp_segments(values: list[str]) -> list[str]:
    """Longest common hyphen-segment prefix across values.
    ['add-to-cart-backpack','add-to-cart-bike-light'] -> ['add','to','cart']."""
    seg_lists = [v.split("-") for v in values]
    common: list[str] = []
    for tup in zip(*seg_lists):
        if all(s == tup[0] for s in tup):
            common.append(tup[0])
        else:
            break
    return common


def collapse_repeated_families(elements: dict[str, dict], min_family: int = 2,
                               test_attrs: tuple = TEST_ID_ATTRS
                               ) -> dict[str, dict]:
    """Collapse test-id values sharing a hyphen-prefix into one prefix match.

    e.g. buy-item-101, buy-item-hard-goods -> a single 'buy_item_buttons' entry
    using [<attr>^='buy-item-'], where <attr> is whichever test-id attribute the
    app actually uses. Members are bucketed by their first two hyphen segments,
    then the exact family prefix is the longest common segment-prefix of the
    bucket (>=2 segments). Only fires for `min_family`+ members sharing the same
    attribute; everything else passes through unchanged.
    """
    buckets: dict[str, list[str]] = {}          # (attr, bucket-key) -> names
    val_by_elem: dict[str, str] = {}
    attr_by_elem: dict[str, str] = {}
    passthrough: dict[str, dict] = {}

    for name, entry in elements.items():
        parsed = _parse_test_attr(entry.get("selector", ""), test_attrs)
        segs = parsed[1].split("-") if parsed else []
        if parsed and len(segs) >= 3:           # need prefix(>=2) + variable(>=1)
            attr, value = parsed
            key = attr + "|" + "-".join(segs[:2])
            buckets.setdefault(key, []).append(name)
            val_by_elem[name] = value
            attr_by_elem[name] = attr
        else:
            passthrough[name] = entry

    out = dict(passthrough)
    for _key, members in buckets.items():
        if len(members) >= min_family:
            prefix_segs = _lcp_segments([val_by_elem[m] for m in members])
            if len(prefix_segs) >= 2:
                prefix = "-".join(prefix_segs)
                attr = attr_by_elem[members[0]]
                fam_name = f"{_slug_to_name(prefix)}_buttons"
                out[fam_name] = {
                    "selector": f"[{attr}^='{prefix}-']",
                    "strategy": f"{attr}-prefix",
                    "family_members_seen": sorted(val_by_elem[m] for m in members),
                }
                continue
        for m in members:                        # too small / no shared prefix
            out[m] = elements[m]
    return out


# ─────────────────────────────────────────────────────────────
# Page assembly (generate)
# ─────────────────────────────────────────────────────────────

def url_to_path(url: str, base_url: str = "") -> str:
    """Normalize an absolute URL to an app-relative path ('/inventory.html')."""
    p = urlparse(url)
    path = p.path or "/"
    if p.query:
        path = f"{path}?{p.query}"
    return path or "/"


def guess_page_object(path: str) -> tuple[str, str]:
    """Guess (page_object_file, PageObjectClass) from a URL path."""
    stem = re.sub(r"\.html?$", "", (path.strip("/").split("?")[0] or "home"))
    stem = _slug_to_name(stem) or "home"
    cls = "".join(part.capitalize() for part in stem.split("_")) + "Page"
    return (f"pages/{stem}_page.py", cls)


def _is_capturable(tag: str, attrs: dict, test_attrs: tuple) -> bool:
    """Should this element become an inventory entry?

    Native interactive tags, anything with a test-id, anything with an
    interactive ARIA role, focusable custom controls (tabindex >= 0), and
    contenteditable widgets. This is what pulls in div-based custom widgets
    (React-Select, MUI, toggles) that older versions silently skipped.
    """
    a = attrs or {}
    if tag in _INTERACTABLE_TAGS:
        return True
    if any(a.get(k) for k in test_attrs):
        return True
    if (a.get("role") or "").lower() in _INTERACTIVE_ROLES:
        return True
    if a.get("contenteditable") in ("", "true"):
        return True
    # a stable, human-authored id is an intent signal — catches id'd custom
    # widgets and drag-drop targets (#draggable) that carry no role/tabindex.
    if a.get("id") and not _looks_generated_id(a["id"]):
        return True
    ti = a.get("tabindex")
    if ti is not None:
        try:
            if int(ti) >= 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def build_page_entry(url: str, title: str, descriptors: list[dict],
                     base_url: str = "", test_attrs: tuple = TEST_ID_ATTRS) -> dict:
    """Assemble a draft page dict (schema-shaped) from DOM descriptors.

    Machine-fillable fields are populated (url, elements, page-object guess);
    human-only fields are emitted as visible stubs (`elements_notes`,
    `key_methods`, page-level `errors`). Captures native controls, custom
    widgets (via ARIA role / tabindex / contenteditable), and elements inside
    iframes (a descriptor's `frame` field becomes a `frame >>> selector` prefix)
    and open shadow DOM. Any element whose only handle is a fragile css fallback
    is listed under `_unstable_selectors` so the reviewer can add a data-test.
    """
    path = url_to_path(url, base_url)
    elements: dict[str, dict] = {}
    used: set[str] = set()

    for d in descriptors:
        tag = (d.get("tag") or "").lower()
        attrs = d.get("attrs") or {}
        text = d.get("text") or ""
        if not _is_capturable(tag, attrs, test_attrs):
            continue
        selector, strategy = rank_selector(tag, attrs, text, test_attrs,
                                           label=d.get("label", ""))
        # Element inside an iframe: prefix with the frame's own selector using
        # the documented `>>>` frame-enter convention.
        frame_sel = d.get("frame")
        if frame_sel:
            selector = f"{frame_sel} {FRAME_DELIM} {selector}"
        name = derive_element_name(tag, attrs, text, test_attrs)
        final = name
        i = 2
        while final in used:
            final = f"{name}_{i}"
            i += 1
        used.add(final)
        elements[final] = {"selector": selector, "strategy": strategy,
                           "framed": bool(frame_sel)}

    elements = collapse_repeated_families(elements, test_attrs=test_attrs)
    clean_elements = {n: e["selector"] for n, e in elements.items()}
    strategies = {n: e.get("strategy", "css") for n, e in elements.items()}
    unstable = sorted(n for n, e in elements.items()
                      if is_unstable_strategy(e.get("strategy", "css")))

    # Selectors emitted for MORE THAN ONE element. Playwright runs locators in
    # strict mode by default, so a selector matching several elements raises
    # "strict mode violation: locator resolved to N elements" at runtime — even
    # though a staleness check (which only looks for ZERO matches) passes it.
    # Names are de-duplicated above, but two different elements can still rank
    # to the same weak selector, so this must be detected separately.
    _by_selector: dict[str, list[str]] = {}
    for n, e in elements.items():
        _by_selector.setdefault(e["selector"], []).append(n)
    ambiguous = {sel: sorted(names) for sel, names in _by_selector.items()
                 if len(names) > 1}

    pof, poc = guess_page_object(path)
    entry = {
        "url": path,
        "components": [],  # human tags these (drives 2.2); left empty in a draft
        "page_object_file": f"{pof} (AUTO-DRAFT — verify)",
        "page_object_class": poc,
        "elements": clean_elements,
        "_selector_strategies": strategies,  # draft aid; delete after review
        "elements_notes": {},   # STUB — fill behavioral quirks by hand
        "key_methods": [],      # STUB — fill intended page-object API by hand
        "errors": {},           # STUB — page-level errors (see 2.2 synergy)
        "implementation_status": (
            "AUTO-GENERATED DRAFT — review every selector, tag `components`, and "
            "add elements_notes / key_methods / errors by hand. Machine cannot "
            "infer behavior, intended API, or exact error strings."
        ),
        "title_seen": title,
    }
    if ambiguous:
        entry["_ambiguous_selectors"] = {
            "selectors": ambiguous,
            "warning": ("Each of these selectors was produced for MORE THAN ONE "
                        "element on this page. Playwright locators are strict by "
                        "default, so using one raises 'strict mode violation: "
                        "locator resolved to N elements' at runtime. Give each "
                        "element a distinct handle (add a data-test attribute) or "
                        "disambiguate with .nth()/.filter() in the page object."),
        }
    if unstable:
        entry["_unstable_selectors"] = {
            "elements": unstable,
            "warning": ("No durable handle found for these — only a fragile css "
                        "fallback. Add a data-test attribute in the app, or replace "
                        "with a role/label/text locator, before relying on them."),
        }
    return entry


# ─────────────────────────────────────────────────────────────
# Staleness diff (check)
# ─────────────────────────────────────────────────────────────

def diff_page(page_name: str, inventory_selectors: dict[str, str],
              live_resolved: dict[str, int], live_data_tests: set[str],
              test_attrs: tuple = TEST_ID_ATTRS) -> dict:
    """Diff one committed page against the live DOM.

    inventory_selectors : {element_name: selector} from the committed inventory
    live_resolved       : {selector: match_count} measured on the live page
    live_data_tests     : set of test-id values actually present on the page

    Returns {"missing": [...], "new_data_tests": [...]} where `missing` are
    inventory selectors that resolve to zero live elements (the dangerous drift)
    and `new_data_tests` are live test-id handles absent from the inventory.
    """
    missing = [
        {"element": name, "selector": sel}
        for name, sel in inventory_selectors.items()
        if live_resolved.get(sel, 0) == 0
    ]
    inv_values = {
        parsed[1] for sel in inventory_selectors.values()
        if (parsed := _parse_test_attr(sel, test_attrs)) is not None
    }
    # also treat prefix selectors ([<attr>^='buy-item-']) as covering the family
    prefixes = [
        parsed[1] for sel in inventory_selectors.values()
        if (parsed := _parse_test_prefix(sel, test_attrs)) is not None
    ]

    def _covered(value: str) -> bool:
        return value in inv_values or any(value.startswith(p) for p in prefixes)

    new = sorted(v for v in live_data_tests if not _covered(v))
    # Live multi-match. Only ZERO matches were previously reported, so a
    # selector resolving to several elements passed silently and then failed at
    # runtime with a Playwright strict-mode violation.
    ambiguous = sorted(
        {"element": name, "selector": sel, "matches": live_resolved.get(sel, 0)}.items()
        and (name, sel, live_resolved.get(sel, 0))
        for name, sel in inventory_selectors.items()
        if live_resolved.get(sel, 0) > 1
    )
    return {"missing": missing, "new_data_tests": new,
            "ambiguous": [{"element": n, "selector": s_, "matches": c}
                          for n, s_, c in ambiguous]}


def summarize_drift(per_page: dict[str, dict], missing_pages: list[str]) -> dict:
    """Roll per-page diffs into a report with an overall `has_drift` flag."""
    total_missing = sum(len(p["missing"]) for p in per_page.values())
    total_new = sum(len(p["new_data_tests"]) for p in per_page.values())
    total_ambiguous = sum(len(p.get("ambiguous", [])) for p in per_page.values())
    return {
        "pages_checked": len(per_page),
        "unreachable_pages": missing_pages,
        "stale_selectors": total_missing,
        "new_untracked_data_tests": total_new,
        # Selectors matching >1 element. Counted as drift because Playwright's
        # strict mode makes them fail at runtime just as surely as a stale one.
        "ambiguous_selectors": total_ambiguous,
        "has_drift": bool(total_missing or missing_pages or total_new
                          or total_ambiguous),
        "pages": per_page,
    }


def pages_missing_notes(inventory: dict) -> list[str]:
    """Pages with no `elements_notes` — the 3.1 'make the gap visible' warning."""
    out = []
    for name, page in (inventory.get("pages") or {}).items():
        if isinstance(page, dict) and not page.get("elements_notes"):
            out.append(name)
    return out