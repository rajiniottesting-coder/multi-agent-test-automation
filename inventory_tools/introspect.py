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


def _looks_generated_id(value: str) -> bool:
    return bool(_GENERATED_ID.search(value or ""))


def _css_escape_value(value: str) -> str:
    return value.replace("'", "\\'")


def rank_selector(tag: str, attrs: dict, text: str = "",
                  test_attrs: tuple = TEST_ID_ATTRS) -> tuple[str, str]:
    """Return (selector, strategy) picking the most stable available handle.

    Priority: a dedicated test-id attribute > stable id > name > aria-label >
    placeholder > role+text > css fallback. `test_attrs` is the ordered list of
    test-id attributes to prefer (defaults to the common conventions). The
    strategy label is informational (surfaced in a draft so a human can see how
    confident the pick is).
    """
    a = attrs or {}
    for key in test_attrs:
        if a.get(key):
            return (f"[{key}='{_css_escape_value(a[key])}']", key)
    if a.get("id") and not _looks_generated_id(a["id"]):
        return (f"#{a['id']}", "id")
    if a.get("name"):
        return (f"{tag}[name='{_css_escape_value(a['name'])}']", "name")
    if a.get("aria-label"):
        return (f"{tag}[aria-label='{_css_escape_value(a['aria-label'])}']", "aria-label")
    if a.get("placeholder"):
        return (f"{tag}[placeholder='{_css_escape_value(a['placeholder'])}']", "placeholder")
    role = a.get("role") or _IMPLICIT_ROLE.get(tag)
    t = (text or "").strip()
    if role and t:
        return (f"role={role}[name='{t[:40]}']", "role+text")
    if a.get("type"):
        return (f"{tag}[type='{_css_escape_value(a['type'])}']", "css")
    return (tag, "css")


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
    return {
        "button": "button", "select": "dropdown", "textarea": "input",
        "a": "link",
    }.get(tag, "element")


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

def _parse_test_attr(selector: str, test_attrs: tuple = TEST_ID_ATTRS):
    """Return (attr, value) if selector is [attr='value'] for a test-id attr."""
    m = re.match(r"\[([a-zA-Z-]+)='([^']+)'\]$", selector)
    if m and m.group(1) in test_attrs:
        return m.group(1), m.group(2)
    return None


def _parse_test_prefix(selector: str, test_attrs: tuple = TEST_ID_ATTRS):
    """Return (attr, prefix) if selector is [attr^='prefix'] for a test-id attr."""
    m = re.match(r"\[([a-zA-Z-]+)\^='([^']+)'\]$", selector)
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


def build_page_entry(url: str, title: str, descriptors: list[dict],
                     base_url: str = "", test_attrs: tuple = TEST_ID_ATTRS) -> dict:
    """Assemble a draft page dict (schema-shaped) from DOM descriptors.

    Machine-fillable fields are populated (url, elements, page-object guess);
    human-only fields are emitted as empty stubs so the gap is visible:
    `elements_notes`, `key_methods`, and page-level `errors` (warn when notes
    are missing rather than silently omit). `test_attrs` selects which test-id
    attributes to prefer/track.
    """
    path = url_to_path(url, base_url)
    elements: dict[str, dict] = {}
    used: set[str] = set()

    for d in descriptors:
        tag = (d.get("tag") or "").lower()
        attrs = d.get("attrs") or {}
        text = d.get("text") or ""
        if tag not in _INTERACTABLE_TAGS and not any(
            attrs.get(k) for k in test_attrs
        ):
            continue  # skip non-interactable, non-tagged noise
        selector, strategy = rank_selector(tag, attrs, text, test_attrs)
        name = derive_element_name(tag, attrs, text, test_attrs)
        # de-duplicate names deterministically
        final = name
        i = 2
        while final in used:
            final = f"{name}_{i}"
            i += 1
        used.add(final)
        elements[final] = {"selector": selector, "strategy": strategy}

    elements = collapse_repeated_families(elements, test_attrs=test_attrs)
    # emit selector strings (drop the strategy detail into a sibling map so the
    # page's `elements` stays the clean name->selector shape the schema uses)
    clean_elements = {n: e["selector"] for n, e in elements.items()}
    strategies = {n: e.get("strategy", "css") for n, e in elements.items()}

    pof, poc = guess_page_object(path)
    return {
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
    return {"missing": missing, "new_data_tests": new}


def summarize_drift(per_page: dict[str, dict], missing_pages: list[str]) -> dict:
    """Roll per-page diffs into a report with an overall `has_drift` flag."""
    total_missing = sum(len(p["missing"]) for p in per_page.values())
    total_new = sum(len(p["new_data_tests"]) for p in per_page.values())
    return {
        "pages_checked": len(per_page),
        "unreachable_pages": missing_pages,
        "stale_selectors": total_missing,
        "new_untracked_data_tests": total_new,
        "has_drift": bool(total_missing or missing_pages or total_new),
        "pages": per_page,
    }


def pages_missing_notes(inventory: dict) -> list[str]:
    """Pages with no `elements_notes` — the 3.1 'make the gap visible' warning."""
    out = []
    for name, page in (inventory.get("pages") or {}).items():
        if isinstance(page, dict) and not page.get("elements_notes"):
            out.append(name)
    return out