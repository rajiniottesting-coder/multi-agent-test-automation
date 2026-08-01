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
# Accessible names / text that look VOLATILE — they contain runtime data, so a
# locator built from them breaks as soon as that data changes:
#   "Welcome back, John Smith"   (user name)
#   "3 items in cart"            (count)
#   "Total: $49.99"              (price)
#   "Updated 2 minutes ago"      (timestamp)
# Such a name is still USED (it may be the only handle available) but the
# strategy is downgraded so the element lands in `_unstable_selectors` and the
# reviewer is told to replace it with a data-test attribute.
_VOLATILE_TEXT = re.compile(
    r"\d"                                  # any digit: counts, prices, dates, ids
    r"|\b(welcome|hello|hi)\b[, ]"          # personalised greetings
    r"|\b(ago|remaining|left)\b",           # relative times / countdowns
    re.IGNORECASE,
)


# A value segment that is clearly runtime-generated: a long digit run, a uuid
# chunk, a hex blob, or a date stamp. An attribute carrying one of these churns
# between runs, so the WHOLE value must never be used as an exact-match locator.
# Prefixes emitted by UI libraries. Anchoring on one matches every element the
# library renders, so it is worthless as a locator.
_FRAMEWORK_ID_PREFIX = re.compile(
    r"^(radix|headlessui|ember|mui|chakra|mantine|ant)$", re.IGNORECASE)

_DYNAMIC_SEGMENT = re.compile(
    r"^\d{3,}$"                       # 8891, 20260725
    r"|^[0-9a-f]{8,}$"                 # a3f8b21c, hex/uuid chunk
    r"|^[0-9a-f]{4,}-[0-9a-f]{4,}",    # uuid-ish pair
    re.IGNORECASE,
)


def dynamic_attr_prefix(value: str) -> str:
    """Return the STABLE leading part of a hyphenated attribute value, or "".

    "user-profile-8891"  -> "user-profile"      (8891 is runtime data)
    "session-a3f8b21c"   -> "session"
    "order-row-20260725" -> "order-row"
    "add-to-cart"        -> ""                  (nothing dynamic — use as-is)

    Callers turn a non-empty result into a starts-with match
    ([data-test^='user-profile-']) so the locator survives the value changing.
    Requires at least one stable segment, otherwise there is nothing to anchor
    on and the caller should fall through to another strategy.
    """
    if not value or "-" not in value:
        return ""
    segs = value.split("-")
    stable = []
    for seg in segs:
        if _DYNAMIC_SEGMENT.match(seg):
            break
        stable.append(seg)
    if not stable or len(stable) == len(segs):
        return ""                       # nothing dynamic, or nothing stable
    return "-".join(stable)


def _is_volatile_text(value: str) -> bool:
    """True if this text embeds runtime data and will churn between runs."""
    return bool(value and _VOLATILE_TEXT.search(value))


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
                  label: str = "", css_path: str = "") -> tuple[str, str]:
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
            val = a[key]
            # Dynamic value (record id, session id, timestamp embedded in it):
            # anchor on the stable prefix instead of the whole churning value.
            prefix = dynamic_attr_prefix(val)
            if prefix:
                return (f"[{key}^='{_css_escape_value(prefix)}-']", f"{key}-prefix")
            return (f"[{key}='{_css_escape_value(val)}']", key)
    if a.get("id") and not _looks_generated_id(a["id"]):
        return (f"#{a['id']}", "id")
    if a.get("id"):
        # The id was rejected as generated, but it may still carry a MEANINGFUL
        # stable prefix worth anchoring on:
        #     "order-row-20260725" -> [id^='order-row-']
        # A FRAMEWORK prefix (radix-, ember-, headlessui-) is not meaningful —
        # every element the library renders shares it — so those are skipped and
        # ranking continues to name/role/label below.
        id_prefix = dynamic_attr_prefix(a["id"])
        if id_prefix and not _FRAMEWORK_ID_PREFIX.match(id_prefix):
            return (f"[id^='{_css_escape_value(id_prefix)}-']", "id-prefix")
    if a.get("name"):
        return (f"{tag}[name='{_css_escape_value(a['name'])}']", "name")
    # accessible role + name — churn-proof, handles custom/div-based widgets.
    role = a.get("role") or _IMPLICIT_ROLE.get(tag)
    acc_name = (a.get("aria-label") or (text or "")).strip()
    # getByRole WITH an accessible name — Playwright's first recommendation.
    # getByRole WITH a STABLE accessible name — Playwright's first choice.
    # If the name is volatile ("3 items in cart") we deliberately do NOT return
    # here: a stable aria-label/placeholder/alt/title further down is a better
    # locator than a name that changes every run. The volatile name is only
    # used later, as a fallback, if nothing stable turns up.
    if role in _INTERACTIVE_ROLES and acc_name and not _is_volatile_text(acc_name):
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
        return (f"role={role}[name='{_css_escape_value(acc_name[:40])}']",
                "role-volatile" if _is_volatile_text(acc_name) else "role")
    # Volatile accessible name — nothing stable was found above, so use it
    # anyway (it is still better than a positional path) but flag it.
    if role in _INTERACTIVE_ROLES and acc_name:
        return (f"role={role}[name='{_css_escape_value(acc_name[:40])}']",
                "role-volatile")
    # Nameless interactive role: churn-proof, but weaker than any named handle
    # above, so it deliberately ranks below label/alt/title.
    if role in _INTERACTIVE_ROLES:
        return (f"role={role}", "role")
    t = (text or "").strip()
    if t and tag in ("a", "button"):
        return (f"text={_css_escape_value(t[:40])}",
                "text-volatile" if _is_volatile_text(t) else "text")
    # LAST RESORT — nothing semantic was available. A bare tag (or tag[type])
    # is a CATEGORY, not a locator: it matches every similar element on the
    # page and fails Playwright's strict mode. Fall back to the structurally
    # unique css path instead, so EVERY element still gets a locator that
    # resolves to exactly one node. It is brittle against layout changes —
    # hence still reported as "css" and flagged in _unstable_selectors — but a
    # brittle locator that works beats a clean one that never can.
    if css_path:
        return (css_path, "css")
    if a.get("type"):
        return (f"{tag}[type='{_css_escape_value(a['type'])}']", "css")
    return (tag, "css")


# strategies that produced a durable handle; anything else ("css") is fragile.
_STABLE_STRATEGIES = set(TEST_ID_ATTRS) | {
    "id", "name", "role", "label", "aria-label", "placeholder", "alt", "title",
    "text", "data-test-prefix", "id-prefix",
    *(f"{a}-prefix" for a in TEST_ID_ATTRS),
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


# Words that carry no meaning in an element name. Stripped from names derived
# from visible TEXT or LABELS, never from a test-id or `name` attribute - those
# are the author's deliberate identifier and are kept exactly as written.
_NAME_STOPWORDS = frozenset({
    "the", "a", "an", "of", "to", "for", "your", "please", "click", "here",
    "this", "that", "and", "or", "is", "are", "be", "on", "in", "at", "it",
})

# Four tokens is enough to be unambiguous; beyond that a name is a sentence.
_MAX_NAME_TOKENS = 4

# `type` values worth folding into a name. An <input type="email"> with no other
# identifier is meaningfully an "email input", not an anonymous "input".
_TYPE_HINTS = frozenset({
    "email", "password", "search", "tel", "url", "number", "date", "file",
})


def _clean_prose_name(value: str) -> str:
    """snake_case a human-readable string into an identifier-sized name.

    Drops stopwords and caps the token count, so "Please enter your e-mail
    address here" becomes `enter_email_address` rather than a sentence. If
    stripping leaves nothing - a label that is entirely stopwords - the
    unstripped form is kept: a slightly noisy name beats no name.
    """
    slug = _slug_to_name(value)
    if not slug:
        return ""
    tokens = slug.split("_")
    kept = [t for t in tokens if t not in _NAME_STOPWORDS]
    tokens = kept or tokens
    return "_".join(tokens[:_MAX_NAME_TOKENS])


def _disambiguate(name: str, used: set, tag: str, attrs: dict,
                  text: str) -> str:
    """A distinguishing name when `name` is already taken.

    A bare counter (`input_2`, `input_3`) tells a reader nothing and all but
    guarantees that whoever writes the page object picks the wrong one. Before
    falling back to that, say HOW this element differs from the one that
    claimed the name - its input type, its visible text, or failing both an
    explicit `_alt`. Returns `name` untouched when there is no collision.
    """
    if name not in used:
        return name
    a = attrs or {}
    candidates = []
    if a.get("type"):
        candidates.append(f"{name}_{_slug_to_name(a['type'])}")
    if text.strip():
        prose = _clean_prose_name(text.strip()[:40])
        if prose:
            candidates.append(f"{prose}_{element_kind(tag, a)}")
    candidates.append(f"{name}_alt")
    for c in candidates:
        if c and c != name and c not in used:
            return c
    return name


def derive_element_name(tag: str, attrs: dict, text: str = "",
                        test_attrs: tuple = TEST_ID_ATTRS,
                        label: str = "") -> str:
    """Human-ish snake_case name from the strongest identifier available.

    Priority, strongest first:

        1. test-id attribute   - the author's own deliberate handle
        2. `name` / aria-label - semantic, stable, author-written
        3. the field's LABEL   - what a human calls this control on screen
        4. placeholder
        5. a non-generated id
        6. visible text
        7. the input `type`    - "email input" beats an anonymous "input"

    The label was already collected for selector ranking and then thrown away
    for naming, which is why anonymous form fields fell through to bare kinds
    and collided into `input_2`, `input_3`. Real applications label their
    fields even when the markup carries no usable attribute, so this is the
    single biggest source of meaningful names.
    """
    a = attrs or {}
    base = ""

    # 1-2. Author-written identifiers: verbatim, no stopword stripping.
    for key in (*test_attrs, "name", "aria-label"):
        if a.get(key):
            base = _slug_to_name(a[key])
            break

    # 3-4. Human-facing text for the control.
    if not base and label.strip():
        base = _clean_prose_name(label)
    if not base and a.get("placeholder"):
        base = _clean_prose_name(a["placeholder"])

    # 5. An id, unless it looks framework-generated.
    if not base and a.get("id") and not _looks_generated_id(a["id"]):
        base = _slug_to_name(a["id"])

    # 6. Visible text (buttons, links).
    if not base and text.strip():
        base = _clean_prose_name(text.strip()[:60])

    kind = element_kind(tag, a)

    # 7. Last resort: let the input type say something.
    if not base:
        itype = (a.get("type") or "").lower()
        if tag == "input" and itype in _TYPE_HINTS:
            base = itype

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
    """Normalize an absolute URL to an app-relative path ('/products')."""
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


# Attributes by which an element ADVERTISES that it reveals hidden content.
# The revealed content (menu items, dialog fields, listbox options) is often not
# rendered until the user interacts, so a DOM snapshot can never see it. These
# controls are the reviewer's to-do list: click each one, then hand-add what
# appears.
_REVEALS_HIDDEN_CONTENT = (
    "aria-haspopup",      # menu / dialog / listbox / tree / grid
    "aria-controls",      # points at a region that may not be rendered yet
    "data-toggle",        # Bootstrap 4
    "data-bs-toggle",     # Bootstrap 5
)

# Roles whose *contents* (options, menu items, tabs) commonly render on demand.
_LAZY_CONTAINER_ROLES = {"combobox", "listbox", "menu", "menubar", "tablist",
                         "tree", "dialog", "alertdialog"}


def reveals_hidden_content(tag: str, attrs: dict) -> str:
    """Return WHY this element likely hides content, or "" if it does not.

    Detects only what the element declares about itself - no clicking, no
    guessing. A collapsed control (aria-expanded="false") or one that opens a
    popup is very likely to have children a static snapshot cannot see.
    """
    a = attrs or {}
    if str(a.get("aria-expanded", "")).lower() == "false":
        return "aria-expanded='false' - collapsed, contents likely not rendered"
    for key in _REVEALS_HIDDEN_CONTENT:
        if a.get(key):
            return f"{key}='{a[key]}' - opens content that may render on demand"
    role = (a.get("role") or "").lower()
    if role in _LAZY_CONTAINER_ROLES:
        return f"role='{role}' - its options/items may render only when opened"
    return ""


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
        reason = reveals_hidden_content(tag, attrs)
        selector, strategy = rank_selector(tag, attrs, text, test_attrs,
                                           label=d.get("label", ""),
                                           css_path=d.get("cssPath", ""))
        # Element inside an iframe: prefix with the frame's own selector using
        # the documented `>>>` frame-enter convention.
        frame_sel = d.get("frame")
        if frame_sel:
            selector = f"{frame_sel} {FRAME_DELIM} {selector}"
        name = derive_element_name(tag, attrs, text, test_attrs,
                                   label=d.get("label", ""))
        final = _disambiguate(name, used, tag, attrs, text)
        i = 2
        while final in used:
            final = f"{name}_{i}"
            i += 1
        used.add(final)
        elements[final] = {"selector": selector, "strategy": strategy,
                           "framed": bool(frame_sel), "reveals": reason}

    elements = collapse_repeated_families(elements, test_attrs=test_attrs)
    # NOTE: built AFTER disambiguation below so the nth= suffixes are included.

    strategies = {n: e.get("strategy", "css") for n, e in elements.items()}
    unstable = sorted(n for n, e in elements.items()
                      if is_unstable_strategy(e.get("strategy", "css")))

    # Selectors emitted for MORE THAN ONE element. Playwright runs locators in
    # strict mode by default, so a selector matching several elements raises
    # "strict mode violation: locator resolved to N elements" at runtime.
    # diff_page() does now count these as drift, so `check` catches them on a
    # committed inventory — this block is what catches them at generate time,
    # before anyone commits.
    # Names are de-duplicated above, but two different elements can still rank
    # to the same weak selector, so this must be detected separately.
    _by_selector: dict[str, list[str]] = {}
    for n, e in elements.items():
        _by_selector.setdefault(e["selector"], []).append(n)
    ambiguous = {sel: sorted(names) for sel, names in _by_selector.items()
                 if len(names) > 1}

    # DISAMBIGUATE duplicates. Ranking is per-element, so three links reading
    # "Canada" each independently rank to role=link[name='Canada'] - a perfectly
    # VALID locator that simply is not UNIQUE, so the concrete css-path fallback
    # never fires (it only triggers when nothing semantic is found at all).
    # Playwright is strict by default, so all three would raise
    # "strict mode violation: resolved to 3 elements" at runtime.
    #
    # Appending ' >> nth=N' (native Playwright syntax, DOM order) keeps the
    # readable semantic locator AND makes it resolve to exactly one node.
    # Preferred over swapping in the raw css path, which is longer and loses
    # the meaning. `_ambiguous_selectors` below still REPORTS the collision so
    # the reviewer knows to add a data-test attribute in the app.
    _seen: dict[str, int] = {}
    _dupes = {sel for sel, names in _by_selector.items() if len(names) > 1}
    for name, entry_e in elements.items():
        sel = entry_e["selector"]
        if sel in _dupes:
            idx = _seen.get(sel, 0)
            entry_e["selector"] = f"{sel} >> nth={idx}"
            _seen[sel] = idx + 1


    # Families the machine can prove: a collapsed prefix entry stands for
    # several real elements by construction. Emitted as a FIRST-CLASS field,
    # not a `_`-prefixed draft aid, because the draft aids get stripped during
    # curation and this fact has to survive into the file Agent 2 reads — a
    # generation-time validator enforces it there. Hand-added family keys
    # (dropdown options, dialog buttons: anything a crawler never sees because
    # it never clicks) must be appended here by hand; `verify_locators` reports
    # which ones by counting live matches.
    multi_match = sorted(n for n, e in elements.items()
                         if e.get("family_members_seen"))

    clean_elements = {n: e["selector"] for n, e in elements.items()}
    pof, poc = guess_page_object(path)
    entry = {
        "url": path,
        "components": [],  # human tags these (drives 2.2); left empty in a draft
        "page_object_file": f"{pof} (AUTO-DRAFT — verify)",
        "page_object_class": poc,
        "elements": clean_elements,
        "multi_match": multi_match,  # KEEP through curation - it is enforced
        "multi_match_note": (
            "Keys whose selector matches SEVERAL elements. Read them with "
            "get_all_texts / get_count / get_nth_text / the table helpers; "
            "never click, fill, wait on or assert against them. A `<key>_first` "
            "sibling, where present, is the same selector pinned '>> nth=0'. "
            "ADD any hand-written family key here - a crawler never clicks, so "
            "options and dialog contents are not in this list yet."
        ),
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
    interaction = {n: e["reveals"] for n, e in elements.items() if e.get("reveals")}
    if interaction:
        entry["_interaction_required"] = {
            "controls": interaction,
            "warning": ("These controls reveal content that a DOM snapshot cannot "
                        "see - a crawler never clicks, so anything rendered on "
                        "demand (menu items, dialog fields, dropdown options) is "
                        "MISSING from this page. Open each control by hand and add "
                        "the elements it reveals before committing."),
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