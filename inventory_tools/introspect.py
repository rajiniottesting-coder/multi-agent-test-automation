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
import re as _re
import unicodedata
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
                  label: str = "", css_path: str = "",
                  visible: bool = True,
                  has_icon_child: bool = False) -> tuple[str, str]:
    """Return (selector, strategy) picking the most stable available handle.

    Priority, following Playwright's own locator recommendations:

        test-id attr
        > role + accessible name  (getByRole)    <- Playwright's first choice
        > label                   (getByLabel)
        > aria-label
        > placeholder             (getByPlaceholder)
        > alt                     (getByAltText)
        > title                   (getByTitle)
        > stable id / name        (css, but an author's deliberate contract)
        > nameless role
        > text                    (getByText)
        > css path fallback

    USER-FACING LOCATORS COME FIRST. `#id` and `[name=…]` are page.locator()
    css, not a getBy* method, and they used to outrank role and label - so a
    labelled form field with an id produced `#email-field` instead of
    getByLabel("Email"), which is the opposite of Playwright's guidance and
    made generated page objects read like 2015-era Selenium. They remain ahead
    of text= and the raw css path, because a deliberate id or name IS a stable
    contract; they are simply not the first thing to reach for.

    Every strategy above the css path fallback maps to a first-class Playwright
    locator. XPath is deliberately never emitted.

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
    # ── ANCHORS: prefer the href over the accessible name ───────────────
    # An <a> carries its destination, and that destination is immune to the
    # markup INSIDE the link. An accessible name is not: an icon font that
    # renders from ligature text prefixes the glyph name onto it, and any
    # decorative span changes it too - the locator then matches nothing.
    # Verified against a live app on 2 Aug 2026: a role+name locator for a
    # per-record link resolved to ZERO while its href matched every card.
    #
    # A trailing runtime id segment becomes a prefix match,
    # which correctly reads as a family; build_page_entry then collapses those
    # into multi_match.
    if tag == "a":
        href = (a.get("href") or "").strip()
        # A FRAGMENT href (#section) is kept: it is exact, stable, and unlike an
        # accessible name it cannot be polluted by icon markup inside the link.
        # Only protocol hrefs are useless as locators.
        if href and not href.startswith(("javascript:", "mailto:", "tel:")):
            last = href.rstrip("/").rsplit("/", 1)[-1]
            if last.isdigit() and len(href.rstrip("/")) > len(last):
                stem = href.rstrip("/")[: -len(last)]
                return (f"a[href^='{_css_escape_value(stem)}']", "href-prefix")
            return (f"a[href='{_css_escape_value(href)}']", "href")

    # ── HIDDEN ELEMENTS HAVE NO ACCESSIBLE ROLE ────────────────────────
    # A collapsed accordion panel, a closed modal, an inactive carousel slide:
    # the DOM has them, so the crawler captures them, but the ACCESSIBILITY
    # TREE does not - and role= / label= / alt= / title= all read that tree.
    # Emitting a role+name locator for a collapsed category produces a
    # locator that resolves to ZERO for as long as the panel stays shut, which
    # is indistinguishable from a broken selector in a staleness report.
    #
    # Verified 4 Aug 2026: a display:none link matched 0 via role= and 1 via
    # css on the same node. So for hidden elements, skip every a11y-tree
    # strategy and go straight to a css handle, which still resolves.
    # ── AN ICON CHILD POISONS THE ACCESSIBLE NAME ──────────────────────
    # A CSS ::before glyph is folded into the accessible name but is invisible
    # to textContent and innerText, so any role=/label=/alt=/title= locator
    # built from the DOM text will not match. Fall through to a handle that
    # does not read the accessibility tree.
    if has_icon_child or not visible:
        if a.get("id") and not _looks_generated_id(a["id"]):
            return (f"#{a['id']}", "id-hidden")
        if a.get("name"):
            return (f"{tag}[name='{_css_escape_value(a['name'])}']", "name-hidden")
        if tag == "a" and (a.get("href") or "").strip():
            return (f"a[href='{_css_escape_value(a['href'].strip())}']", "href-hidden")
        if css_path:
            return (css_path, "css-path-hidden")

    # accessible role + name — churn-proof, handles custom/div-based widgets.
    #
    # An <a> WITHOUT href has no link role at all (ARIA maps it to `generic`),
    # so emitting role=link[name='...'] for one produces a locator that can
    # never match. That is exactly how a checkout control styled as a button
    # shipped as role=link and resolved to zero.
    role = a.get("role") or _IMPLICIT_ROLE.get(tag)
    if tag == "a" and not a.get("role") and not (a.get("href") or "").strip():
        role = None
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
    # ── CSS tier ────────────────────────────────────────────────────
    # `#id` and `[name=…]` are page.locator() CSS, not a getBy* method, so they
    # sit BELOW every user-facing Playwright locator above. They used to sit at
    # the top, which meant a form field with both an id and a label produced
    # `#email-field` rather than getByLabel("Email") — the opposite of what
    # Playwright recommends, and the reason generated page objects looked like
    # 2015-era Selenium. They stay ahead of text= and raw css because a
    # deliberate id or name IS an author's stable contract; they are simply not
    # the FIRST choice.
    if a.get("id") and not _looks_generated_id(a["id"]):
        return (f"#{a['id']}", "id")
    if a.get("id"):
        # The id was rejected as generated, but it may still carry a MEANINGFUL
        # stable prefix worth anchoring on:
        #     "order-row-20260725" -> [id^='order-row-']
        # A FRAMEWORK prefix (radix-, ember-, headlessui-) is not meaningful —
        # every element the library renders shares it — so those are skipped.
        id_prefix = dynamic_attr_prefix(a["id"])
        if id_prefix and not _FRAMEWORK_ID_PREFIX.match(id_prefix):
            return (f"[id^='{_css_escape_value(id_prefix)}-']", "id-prefix")
    if a.get("name"):
        return (f"{tag}[name='{_css_escape_value(a['name'])}']", "name")
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

# Latin letters that Unicode does not decompose into base letter + accent, so
# NFKD alone would drop them. Written out the conventional way.
_FOLD_SPECIAL = str.maketrans({
    "ß": "ss", "ẞ": "SS", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
    "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
    "þ": "th", "Þ": "TH", "ð": "d", "Ð": "D", "ı": "i",
})


def fold_to_ascii(value: str) -> str:
    """Latin-script text with its accents removed: 'Größe wählen' -> 'Grosse wahlen'.

    Element names are ASCII snake_case. Text from an application in German,
    French, Spanish, Polish and the like used to be cut at every accented
    letter, so 'Größe wählen' became 'gr_e_w_hlen'. Folding first keeps the
    word. The same function folds a story's text before it is matched against
    element names, so both sides agree.

    Scripts with no Latin form (Cyrillic, Greek, CJK, Arabic) are left as they
    are; the name builder then drops them as before, and other naming sources
    (test ids, ids, the element kind) take over.
    """
    value = (value or "").translate(_FOLD_SPECIAL)
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _slug_to_name(value: str) -> str:
    """'add-to-cart-backpack' / 'firstName' / 'Größe wählen' -> snake_case token."""
    value = fold_to_ascii(value)
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


# A repeated widget produces one element per instance. Left alone that is 68
# keys named row_link, row_link_2, row_link_3 ... which is worse
# than useless: a test cannot know which index is a given record, every one
# spends prompt tokens on every generated file, and the family that a validator
# should be protecting is invisible because nothing declares it.
#
# `collapse_repeated_families` above only fires on TEST-ID attributes. An app
# with no data-test attributes gets no collapsing at all, which is how 68 keys
# reached a draft.
# Frame ids used by the common ad networks. Matched against the FRAME's own
# selector because nothing inside the frame can see its container.
_AD_FRAME_ID = _re.compile(r"(aswift|google_ads|div-gpt-ad|doubleclick|adsbygoogle)",
                           _re.I)

_MIN_COLLAPSE = 3
_INDEX_SUFFIX = _re.compile(r"(_alt|_\d+)$")
_NTH_SUFFIX = _re.compile(r"\s*>>\s*nth=\d+\s*$")



# Selectors that differ ONLY in an integer are one repeated widget.
_DIGITS = _re.compile(r"\d+")
_NTH_OF_TYPE = _re.compile(r":nth-of-type\(\d+\)")


def _structural_signature(selector: str) -> str:
    """A selector with every integer blanked. Siblings of one widget share it."""
    return _DIGITS.sub("#", selector)


def _family_handle(selectors: list) -> str:
    """A selector matching EVERY member, widened ONLY where they differ.

    Stripping every `:nth-of-type(N)` was far too blunt: a ten-deep path
    became `#app > div > div > ... > div`, which matches most of the page
    rather than the seven rows it came from. Every ancestor the members SHARE
    must stay pinned - they are what makes the handle mean "these rows" and
    not "any div".

    Only the segment that actually varies is widened, so
    `... > div:nth-of-type(3) > div:nth-of-type(6) > span` and
    `... > div:nth-of-type(3) > div:nth-of-type(7) > span` yield
    `... > div:nth-of-type(3) > div > span`.
    """
    if not selectors:
        return ""
    parts = [[seg.strip() for seg in sel.split(">")] for sel in selectors]
    if len({len(p) for p in parts}) != 1:
        return ""                       # different depths: not one widget
    out = []
    for segs in zip(*parts):
        if len(set(segs)) == 1:
            out.append(segs[0])         # shared - keep it pinned
        else:
            widened = _NTH_OF_TYPE.sub("", segs[0]).strip()
            if not widened:
                return ""               # nothing left to match on
            out.append(widened)
    return " > ".join(out)


def _common_suffix_name(names: list) -> str:
    """The trailing words every member shares.

    Members named after DATA - `0455_first_person_row`, `0387_second_person_row` -
    have nothing in common at the front and the meaningful noun at the back.
    """
    parts = [n.split("_") for n in names]
    tail = []
    for i in range(1, min(len(p) for p in parts) + 1):
        token = parts[0][-i]
        if all(p[-i] == token for p in parts):
            tail.insert(0, token)
        else:
            break
    return "_".join(tail)



# A name that is only the element's TAG, or a framework-generated id, carries
# no purpose. Numeric and index suffixes are stripped before the comparison so
# `element_alt`, `input_2` and `button_button` are judged as `element`,
# `input`, `button`.
_MEANINGLESS_NAMES = frozenset({
    "element", "elements", "input", "inputs", "button", "buttons", "link",
    "links", "div", "span", "checkbox", "checkboxs", "checkboxes", "select",
    "selects", "svg", "svgg", "path", "paths", "icon", "icons", "image",
    "images", "label", "labels", "text", "item", "items", "row", "rows",
    "cell", "cells", "container", "wrapper", "app",
})
_GENERATED_NAME = _re.compile(
    r"^(path|svgg?|g|rect|circle|use|clip)[-_]?\d*(_element)?s?$", _re.I)


def _is_meaningless_name(name: str) -> bool:
    """True when the key tells a reader nothing about the element's purpose.

    `element_alt`, `button_button`, `path4_elements` all resolve perfectly
    well. That is the trap: they pass every check, cost prompt tokens on every
    generated file, and give a generator no way to know what they are for - so
    it either ignores them or uses one wrongly. `5_button` was the same shape,
    and it was a page number.

    A name earns its place by saying what the thing IS. Nothing here does.
    """
    stem = _re.sub(r"(_alt|_\d+)$", "", (name or "").strip().lower())
    stem = _re.sub(r"^(\d+)_", "", stem)
    if not stem:
        return True
    if stem in _MEANINGLESS_NAMES or _GENERATED_NAME.match(stem):
        return True
    # `button_button`, `checkbox_checkbox`: the tag repeated, still no purpose.
    parts = stem.split("_")
    return len(set(parts)) == 1 and parts[0] in _MEANINGLESS_NAMES


def split_unnameable(elements: dict, keep: set = frozenset()) -> tuple:
    """Move elements whose KEY carries no purpose into a review block.

    Flag, do not invent and do not silently drop - the same contract as
    `_selectors_to_improve`. The selector is preserved verbatim, so anything a
    test actually needs can be named and moved back in one edit.

    `keep` protects names the page depends on elsewhere - a declared family, a
    readiness anchor - which must never be moved out from under a reference.
    """
    named, unnameable = {}, {}
    for name, entry in (elements or {}).items():
        if name in keep or not _is_meaningless_name(name):
            named[name] = entry
        else:
            unnameable[name] = entry
    return named, unnameable


def collapse_structural_siblings(elements: dict, min_family: int = _MIN_COLLAPSE
                                 ) -> tuple:
    """Collapse N siblings of one repeated widget into a single family key.

    `collapse_indexed_families` groups by NAME STEM - `row`, `row_2`, `row_3`.
    That catches a widget whose members the ranker could not tell apart, and
    misses the commoner case entirely: when each member HAS distinguishing
    text, every one gets its own name. A table of 50 employees produced 50
    keys called `0455_first_person_row`, `0387_second_person_row` and so on - fifty
    different stems, so the name-based collapse never saw a family at all.

    Those keys are worse than useless. Each is named after a record that will
    be edited or deleted by someone else, so it goes stale on its own; and
    fifty of them cannot answer "how many rows are there", which one family
    key answers with get_count(). On a shared demo the record count changed
    twice in the few minutes it took to look at one page.

    The signal is REPETITION, not uniqueness. Selectors that are identical
    except for one integer are siblings of one widget, whatever their members
    are called - and blanking the positional part of any member's path yields
    a handle that matches them all.

    Returns (elements, families, collapsed_report, needs_handle).
    """
    by_sig: dict = {}
    for name, entry in elements.items():
        sel = entry.get("selector") or ""
        if not sel or not _DIGITS.search(sel):
            continue
        by_sig.setdefault(_structural_signature(sel), []).append(name)

    out = dict(elements)
    families: list = []
    report: dict = {}
    unhandled: dict = {}

    for sig, members in by_sig.items():
        if len(members) < min_family:
            continue
        members = sorted(members)
        base = _common_suffix_name(members)
        if not base:
            # Nothing in the names agrees. Collapsing would produce a key
            # nobody can read, and a bad name is worse than several honest
            # ones - leave them and let a human look.
            continue

        first = elements[members[0]]
        member_sel = first.get("selector") or ""
        handle = _family_handle([elements[m].get("selector") or ""
                                 for m in members])
        if not handle or handle == member_sel:
            # Widening changed nothing, so there is no selector that matches
            # the family - only the first member's. `role=button[name='1']`
            # is the shape: the integer IS the accessible name, and no amount
            # of blanking makes it match name='2'.
            #
            # Emitting it anyway would be the worst outcome available: a key
            # called `buttons` that silently resolves to ONE element, passing
            # every check while meaning something false. Report it and leave
            # the members alone - a human can supply the real handle, usually
            # a shared class the ranker never looked at.
            unhandled[base or "family"] = {
                "count": len(members),
                "members": members[:3] + ([f"...{len(members) - 3} more"]
                                          if len(members) > 3 else []),
                "reason": (
                    "These are one repeated widget - their selectors differ "
                    "only by an integer - but no selector matches them all: "
                    "the varying part is the element's NAME, not its "
                    "position. Find the class or attribute the members share "
                    "(devtools: inspect two of them and compare), add it as "
                    "ONE key declared multi_match, and delete these. Check it "
                    "first with: verify_locators --selector \"<handle>\" "
                    "--url <this page>"),
            }
            continue

        key = base if base.endswith("s") else base + "s"
        while key in out and key not in members:
            key = "_" + key

        for m in members:
            out.pop(m, None)
        out[key] = {"selector": handle, "strategy": "structural-family",
                    "framed": first.get("framed", False),
                    "reveals": first.get("reveals")}
        families.append(key)
        report[key] = {
            "count": len(members),
            "handle": handle,
            "was": members[:3] + ([f"...{len(members) - 3} more"]
                                  if len(members) > 3 else []),
            "note": (
                "One repeated widget, not several elements: these selectors "
                "differed only by position. The members were named after the "
                "DATA they happened to contain, so each would go stale on its "
                "own as records change. Read the set with get_count() or "
                "get_all_texts(); reach ONE member by the text it contains "
                "with click_in_row(), never by index. If this collapse is "
                "wrong, the members are listed above."),
        }
    return out, families, report, unhandled


def collapse_indexed_families(elements: dict[str, dict],
                              min_family: int = _MIN_COLLAPSE
                              ) -> tuple[dict[str, dict], list[str], list[str]]:
    """Collapse `name`, `name_alt`, `name_2` ... back into one family key.

    Returns (elements, family_names, needs_shared_handle).

    Two shapes, deliberately treated differently:

    SHARED BASE - every member is the same selector with a different `>> nth=`.
        The base matches them all, so the family key IS that base and the
        collapse loses nothing.

    DISTINCT SELECTORS - each member got its own structural css path, because
        the ranker found no durable handle for any of them. There is no
        selector that matches the family, so collapsing would invent one.
        Instead the FIRST member is kept as a representative and the rest are
        dropped, with the name reported so a human can add a real handle (a
        class, or a data-test in the app). Keeping 67 unusable paths to avoid
        admitting one gap is the worse trade.
    """
    by_stem: dict[str, list[str]] = {}
    for name in elements:
        by_stem.setdefault(_INDEX_SUFFIX.sub("", name), []).append(name)

    out: dict[str, dict] = {}
    families: list[str] = []
    needs_handle: list[str] = []

    for name, entry in elements.items():
        stem = _INDEX_SUFFIX.sub("", name)
        members = by_stem[stem]
        if len(members) < min_family:
            out[name] = entry
            continue
        if name != members[0]:
            continue                      # folded into the representative

        bases = {_NTH_SUFFIX.sub("", elements[m].get("selector", "")) for m in members}
        family_name = _plural(stem)
        if len(bases) == 1:
            base = bases.pop()
            out[family_name] = {**entry, "selector": base}
            families.append(family_name)
        else:
            out[family_name] = dict(entry)
            families.append(family_name)
            needs_handle.append(family_name)

    return out, families, needs_handle


def _plural(stem: str) -> str:
    """`row_link` -> `row_links`; leave an existing plural alone."""
    return stem if stem.endswith("s") else stem + "s"


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
    """Normalize an absolute URL to an app-relative path ('/some/path')."""
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
    hidden_names: set[str] = set()
    third_party_names: set[str] = set()

    for d in descriptors:
        tag = (d.get("tag") or "").lower()
        attrs = d.get("attrs") or {}
        text = d.get("text") or ""
        if not _is_capturable(tag, attrs, test_attrs):
            continue
        reason = reveals_hidden_content(tag, attrs)
        # `visible` is measured by the browser during capture. It was recorded
        # and then discarded, which is how ~40 hidden elements shipped with
        # role= selectors that could never resolve.
        is_visible = d.get("visible", True)
        selector, strategy = rank_selector(tag, attrs, text, test_attrs,
                                           label=d.get("label", ""),
                                           css_path=d.get("cssPath", ""),
                                           visible=is_visible,
                                           has_icon_child=d.get("hasIconChild", False))
        # Element inside an iframe: prefix with the frame's own selector using
        # the documented `>>>` frame-enter convention.
        frame_sel = d.get("frame")
        # An element inside an AD IFRAME is third-party, and `el.closest()`
        # cannot see that: it stops at the document boundary, exactly as it
        # stopped at a shadow root. The frame's own selector is the only
        # evidence available here, so match on it. Without this, one crawl put
        # ~30 keys on a page - doubleclick tracking links, mute panels,
        # `#abgc`, `#mys-wrapper` - all of them ad chrome, none of them the
        # application.
        in_ad_frame = bool(frame_sel and _AD_FRAME_ID.search(frame_sel))
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
        if not is_visible:
            hidden_names.add(final)
        if d.get("thirdParty") or in_ad_frame:
            third_party_names.add(final)
        elements[final] = {"selector": selector, "strategy": strategy,
                           "framed": bool(frame_sel), "reveals": reason}

    elements = collapse_repeated_families(elements, test_attrs=test_attrs)

    # Then collapse REPEATED WIDGETS - one element per product card, per table
    # row, per carousel slide. The test-id collapse above cannot see these:
    # an app with no data-test attributes produced 68 keys named
    # row_link, row_link_2 ... which no test can use and which cost
    # prompt tokens on every generated file.
    elements, _measured_families, _needs_handle = collapse_indexed_families(elements)

    # Then the members the NAME-based collapse cannot see. It groups by stem,
    # so it only catches a widget whose members the ranker could not tell
    # apart; when each member has distinguishing text they get distinct names
    # and distinct stems, and fifty table rows arrive as fifty unrelated keys.
    elements, _struct_families, _collapsed, _unhandled = \
        collapse_structural_siblings(elements)
    _measured_families = list(_measured_families) + _struct_families

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
            "never click, fill, wait on or assert against the family AS A WHOLE. To act on ONE member, scope to the row containing its text with click_in_row(). A `<key>_first` "
            "sibling, where present, is the same selector pinned '>> nth=0'. "
            "ADD any hand-written family key here - a crawler never clicks, so "
            "options and dialog contents are not in this list yet."
        ),
        "_selector_strategies": strategies,  # draft aid; delete after review
        # STUB. Name the element that proves this page loaded, in EVERY state
        # it can be in. A heading a search replaces, or a banner that only
        # shows when a list is empty, is true in one state and false in
        # another - a probe built on one reports "not loaded" for a page that
        # loaded perfectly well. Only a human who has seen the page in each
        # state can choose it, which is why it is left empty.
        "readiness": "",
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
    # Elements that were HIDDEN at capture time are, by definition, only
    # reachable after an interaction — expanding an accordion, opening a modal,
    # advancing a carousel. That is exactly what `conditional` means, so the
    # draft declares them rather than leaving a human to rediscover it from a
    # wall of STALE lines. Pre-declaring them also means verify_locators reads
    # them as COND (expected) instead of reporting them as faults.
    if _measured_families:
        declared = set(entry.get("multi_match") or [])
        entry["multi_match"] = sorted(declared | set(_measured_families))
        entry.setdefault("multi_match_note",
                         "Keys whose selector matches SEVERAL elements - one per "
                         "product card, table row or carousel slide. Read them with "
                         "the plural helpers; to act on ONE member use click_in_row(). Never click, fill or assert on "
                         "one directly. Collapsed from per-instance keys at crawl "
                         "time.")
    if _collapsed:
        entry["_collapsed_families"] = {
            "_why": (
                "Each of these was several keys named after the DATA a "
                "repeated widget happened to contain. They are listed so you "
                "can check the collapse was right - if it was not, restore "
                "them from this block."),
            **_collapsed,
        }
    if _unhandled:
        entry["_repeated_widgets_needing_a_handle"] = {
            "_why": (
                "One repeated widget each, with NO selector that matches all "
                "its members. Nothing was collapsed and nothing was deleted: "
                "inventing a handle here would produce a key that silently "
                "matches one element. Supply the shared class or attribute, "
                "declare it multi_match, then delete the members."),
            **_unhandled,
        }
    if _needs_handle:
        entry["_families_without_a_shared_handle"] = {
            "elements": sorted(_needs_handle),
            "warning": ("Each of these is a repeated widget whose instances had NO "
                        "selector in common - every one fell back to its own "
                        "structural path, so there is no locator that matches the "
                        "family. One instance is kept as a representative and the "
                        "rest were dropped. Give the widget a stable class or a "
                        "data-test attribute in the app, then re-crawl. Until then "
                        "a test can reach these only one instance at a time."),
        }

    if hidden_names:
        entry["conditional"] = sorted(hidden_names)
        entry["conditional_note"] = (
            "AUTO-DETECTED: these were not visible when the page was crawled, so "
            "they sit behind an interaction (a collapsed panel, a closed modal, an "
            "inactive carousel slide). A tool that only navigates will always read "
            "them as absent - that is its reach, not a broken selector. Confirm "
            "each one is genuinely interaction-gated and delete any that are not."
        )
    # Surfaced for a human to delete, not deleted here. The detection is a
    # heuristic about embed containers, so it can miss a network or catch a
    # real element sitting in a similarly-named div - deciding on a guess is
    # exactly what the draft-review step exists to prevent.
    if third_party_names:
        entry["_third_party_elements"] = {
            "elements": sorted(third_party_names),
            "warning": ("These sit inside a THIRD-PARTY embed container (ad or "
                        "recommendation widget). Their text is rotated per "
                        "impression, so each is stale by the next page load and "
                        "none belongs to the application under test. DELETE them "
                        "from this draft unless you can see a reason to keep one - "
                        "the detection is a heuristic and can be wrong either way."),
        }
    if unstable:
        entry["_unstable_selectors"] = {
            "elements": unstable,
            "warning": ("No durable handle found for these — only a fragile css "
                        "fallback. Add a data-test attribute in the app, or replace "
                        "with a role/label/text locator, before relying on them."),
        }
    # Set aside the keys that carry no PURPOSE - LAST, once every analysis
    # block above has been built from the full set. Running it earlier hid
    # these elements from the ambiguity and instability reports, which is
    # exactly where an unnamed duplicate input most needs to be seen.
    #
    # They resolve, which is what makes them dangerous: `element_alt` and
    # `path4_elements` pass every check, cost prompt tokens on every generated
    # file, and give a generator no way to know what they are for. Declared
    # families are protected - a collapsed key may be named `rows`, generic in
    # isolation and exactly what the page needs.
    _kept, _unnameable = split_unnameable(
        entry["elements"], keep=set(entry.get("multi_match") or []))
    entry["elements"] = _kept

    if _unnameable:
        entry["_unnameable_elements"] = {
            "_why": (
                "Nothing on these gave them a purpose - no test hook, id, "
                "role, label or text - so the crawler could only name them "
                "after their tag. They RESOLVE, which is what makes them a "
                "trap: they pass every check, cost prompt tokens on every "
                "generated file, and a key called `element_alt` gives a "
                "generator no way to know what it is for. Name the ones a "
                "test needs and move them back into `elements`; delete the "
                "rest. Nothing has been lost - the selectors are below."),
            # By this point an element's value is the selector STRING, not the
            # {selector, strategy, ...} dict it was earlier in the pipeline.
            **{k: (v.get("selector") if isinstance(v, dict) else v)
               for k, v in _unnameable.items()},
        }

    return entry


# ─────────────────────────────────────────────────────────────
# Staleness diff (check)
# ─────────────────────────────────────────────────────────────

def diff_page(page_name: str, inventory_selectors: dict[str, str],
              live_resolved: dict[str, int], live_data_tests: set[str],
              test_attrs: tuple = TEST_ID_ATTRS,
              declared_family: set | None = None,
              declared_conditional: set | None = None) -> dict:
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

    # Likewise a key declared `conditional` exists only after an interaction,
    # and this tool never clicks - zero matches is the correct reading.
    conditional = declared_conditional or set()
    missing = [m for m in missing
               if (m.get("element") if isinstance(m, dict) else m) not in conditional]

    new = sorted(v for v in live_data_tests if not _covered(v))
    # Live multi-match. Only ZERO matches were previously reported, so a
    # selector resolving to several elements passed silently and then failed at
    # runtime with a Playwright strict-mode violation.
    # A key DECLARED multi_match is meant to match several elements - that is
    # the declaration being satisfied, not drift, and the generation-time
    # validator already stops anyone clicking it. Reporting it as ambiguous
    # every night trains the reader to ignore the report.
    family = declared_family or set()
    ambiguous = sorted(
        (name, sel, live_resolved.get(sel, 0))
        for name, sel in inventory_selectors.items()
        if live_resolved.get(sel, 0) > 1 and name not in family
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


# ─────────────────────────────────────────────────────────────
# Compare mode (check_inventory_staleness --compare)
# ─────────────────────────────────────────────────────────────
#
# The test-id check above only sees NEW elements that carry a test-id
# attribute. An element added without one - a new button, a new required
# field - is invisible to it, so the inventory never learns of it and Agent 0
# gets no seed when it appears (design E1). Compare mode closes that gap by
# DOM IDENTITY, not by guessing: the browser marks every node an inventory
# selector resolves to with COVER_ATTR, then takes the normal capture
# snapshot. Whatever the crawler would capture and is NOT marked is an element
# the inventory does not cover.

COVER_ATTR = "data-inventory-covered"


def uncovered_descriptors(descriptors: list[dict]) -> list[dict]:
    """The descriptors no inventory selector resolved to (pure).

    A descriptor is covered when the browser marked its node with COVER_ATTR.
    Only unmarked descriptors are returned, so the mark can never reach a
    selector or a name built from their attributes."""
    return [d for d in descriptors if COVER_ATTR not in (d.get("attrs") or {})]


def uncovered_elements(url: str, title: str, descriptors: list[dict],
                       base_url: str = "", test_attrs: tuple = TEST_ID_ATTRS) -> dict:
    """{name: selector} for capturable elements no inventory selector covers.

    Built with build_page_entry - the generator's own rules - so a reported
    element is exactly what a fresh crawl would have drafted: the same
    capturability filter, ranked selector and name. Third-party embeds (ad
    networks), which the generator keeps but flags, are left out: they are
    not part of the application. Report only - never drift."""
    entry = build_page_entry(url, title, uncovered_descriptors(descriptors),
                             base_url=base_url, test_attrs=test_attrs)
    third_party = set((entry.get("_third_party_elements") or {}).get("elements") or [])
    return {name: (value.get("selector") if isinstance(value, dict) else value)
            for name, value in (entry.get("elements") or {}).items()
            if not name.startswith("_") and name not in third_party}


def pages_missing_notes(inventory: dict) -> list[str]:
    """Pages with no `elements_notes` — the 3.1 'make the gap visible' warning."""
    out = []
    for name, page in (inventory.get("pages") or {}).items():
        if isinstance(page, dict) and not page.get("elements_notes"):
            out.append(name)
    return out

# A css path this deep is not a locator, it is a description of where an
# element happened to sit during one page load. Ad slots and lazy content shift
# sibling indices between loads, so `div:nth-of-type(14) > div > p > div` is
# stale as soon as anything above it renders differently.
_FRAGILE_PATH_DEPTH = 6


def _is_fragile_path(selector: str) -> bool:
    """True if this is a long structural css path rather than a real handle."""
    if not selector:
        return False
    # a11y-tree and attribute handles are stable by construction
    if selector.startswith(("role=", "text=", "label=", "placeholder=",
                            "alt=", "title=")):
        return False
    # A BARE id is a handle. `#host > div > div:nth-of-type(3)` is a path that
    # merely starts at one - the descendants still encode sibling position.
    has_descendants = ">" in selector or " " in selector.strip()
    if selector.startswith("#") and not has_descendants:
        return False
    if "[" in selector and "]" in selector and not has_descendants:
        return False
    return (selector.count(">") >= _FRAGILE_PATH_DEPTH
            or "nth-of-type" in selector
            or "nth-child" in selector)


def verify_entry_against_page(page, entry: dict) -> dict:
    """Measure every selector against the live page it came from.

    WHY THIS EXISTS
        Ranking has to PREDICT what Playwright will do. It reads DOM
        properties and infers the locator that should match. Every prediction
        it got wrong shipped a selector that resolved to nothing:

          - innerText carries CSS text-transform; the accessible name does not
          - a CSS ::before glyph joins the accessible name, invisible to the DOM
          - a hidden element is absent from the accessibility tree entirely
          - an <a> without href has no link role to match on

        Four separate bug classes, one cause. The page is still open at this
        point, so the guess can simply be replaced with a measurement.

    WHAT IT DOES NOT DO
        It does not repair anything. A selector that fails here is recorded in
        `_unresolved_selectors` for a human to fix, because the right handle
        depends on what the element IS - which the crawler cannot know. Silently
        substituting a css path would trade a visible failure for an invisible
        brittleness.

    Counts are also recorded, so a genuine family is declared as `multi_match`
    from measured evidence rather than from a later staleness sweep.
    """
    elements = entry.get("elements") or {}
    if not elements:
        return entry

    unresolved: list[dict] = []
    measured_family: list[str] = []
    fragile: list[dict] = []

    for name, selector in elements.items():
        try:
            count = _count_on_page(page, selector)
        except Exception as exc:                        # noqa: BLE001
            unresolved.append({"element": name, "selector": selector,
                               "matches": -1, "error": type(exc).__name__})
            continue
        if count == 0:
            unresolved.append({"element": name, "selector": selector, "matches": 0})
        elif count > 1:
            measured_family.append(name)
        elif _is_fragile_path(selector):
            # Resolves TODAY, but only because nothing above it moved. Worth
            # surfacing while the page is open rather than after a layout shift
            # turns it into a mystery STALE line.
            fragile.append({"element": name, "selector": selector})

    if unresolved:
        entry["_unresolved_selectors"] = {
            "elements": unresolved,
            "warning": ("MEASURED on the live page at crawl time: these matched "
                        "ZERO elements, so they are wrong as written and no test "
                        "can use them. Replace each with a handle that does not "
                        "depend on the accessibility tree - an id, a name, an "
                        "href, or a data-test attribute added to the app - and "
                        "re-verify. Do not simply delete them: the element exists, "
                        "only the locator is wrong."),
        }

    if fragile:
        entry["_fragile_selectors"] = {
            "elements": fragile,
            "warning": ("These resolve right now, but only as a STRUCTURAL PATH - "
                        "they describe where an element sat during this crawl, not "
                        "what it is. Any content that renders above them shifts the "
                        "sibling indices and they break silently. Replace with an "
                        "id, name, href or a data-test added to the app. If the "
                        "element belongs to a third-party embed, delete it instead."),
        }

    if measured_family:
        declared = set(entry.get("multi_match") or [])
        entry["multi_match"] = sorted(declared | set(measured_family))
        entry.setdefault("multi_match_note",
                         "Keys whose selector matches SEVERAL elements. Read them "
                         "with the plural helpers; to act on ONE member use click_in_row(). Never click, fill or assert "
                         "on one directly. MEASURED at crawl time, not guessed.")
    return entry


def _count_on_page(page, selector: str) -> int:
    """How many elements this selector resolves to, right now."""
    from inventory_tools.browser import _resolve_one
    return _resolve_one(page, selector).count()