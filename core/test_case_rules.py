"""Rules every drafted test case must follow, checked before it reaches the tracker.

Agent 1 used to write the model's draft straight into the tracker. Two kinds of
test case then passed human approval and failed later, in code generation or in
the browser:

1. A test case that depends on another one: "continue in the same session",
   "the cart holds what the previous scenario added". Every test runs on its own
   in a fresh browser, in any order, so that starting state never exists.
2. An absolute claim about state the application keeps between runs: "exactly
   one row", "only the other product", "the cart is empty". The inventory marks
   such pages `persistent_state`, a shared account or an earlier run can leave
   anything there, and the code-generation gate refuses these claims anyway, so
   the approved text and the code then disagree.

3. An exact quantity on such a page in a test case that signs in with a SHARED
   account: "a row for '<item>' with quantity 1". The state is kept against the
   account, so a run that died before removing '<item>' leaves it there and the
   next run reads 2. The code-generation gate refuses an exact value read from a
   persistent page whenever the scenario signs in, so a test case asking for one
   reaches human approval and then cannot be coded - every repair attempt fails
   the same rule. A test case that never signs in starts from a fresh, empty
   session and may state a quantity: the two gates draw the line in the same
   place. Shared accounts come from the inventory's `test_users`.

All are found here, deterministically, so the draft goes back to the model with
the problems listed instead of reaching a reviewer.

Generic on purpose: the dependency phrases are plain English about tests, and the
persistent pages and shared accounts come from the inventory, so nothing here
names an application.
"""
from __future__ import annotations

import re

# Phrases that tie one test case to another. Checked in every text field.
_DEPENDENCY = [
    (re.compile(r"\b(previous|prior|preceding|earlier)\b[^.\n]{0,40}?\b(tests?|scenarios?|cases?|runs?)\b",
                re.IGNORECASE), "it refers to another test or an earlier run"),
    (re.compile(r"\bsame\s+(?:incognito\s+|private\s+|browser\s+)*session\b", re.IGNORECASE),
     "it continues another test's session"),
    (re.compile(r"\bcontinu\w*\s+(?:in|from|with)\s+the\s+(?:same|previous)\b", re.IGNORECASE),
     "it continues another test"),
    (re.compile(r"\b(?:left|remaining)\s+(?:behind\s+|over\s+)?(?:from|by)\s+(?:the\s+|an?\s+)?"
                r"(?:previous|earlier|another|other)\b", re.IGNORECASE),
     "it relies on state another test left behind"),
]

# "No row(s)": absolute when it speaks of the page's rows as a whole, relative
# when its clause names an entry this test added or removed - decided by
# _absence_of_a_named_entry(), by meaning, not by the words around it.
_NONE_PATTERN = re.compile(r"\bno\s+rows?\b|\bzero\s+rows?\b|\bnone\s+of\s+the\s+rows\b",
                           re.IGNORECASE)

# Absolute claims. Checked only in sentences that mention a persistent page.
_ABSOLUTE = [
    (re.compile(r"\bexactly\b", re.IGNORECASE), "'exactly'"),
    (re.compile(r"\bonly\b", re.IGNORECASE), "'only'"),
    (re.compile(r"\b(?:a\s+)?single\s+rows?\b|\bone\s+row\b|\b\d+\s+rows?\b"
                r"|\bno\s+other\s+rows?\b", re.IGNORECASE), "a row count"),
    (_NONE_PATTERN, "a row count"),
    (re.compile(r"\b(?:is|are|be|remains?|becomes?|left)\s+empty\b", re.IGNORECASE), "'empty'"),
    (re.compile(r"\brather\s+than\s+(?:two|three|\d+|a\s+second)\b", re.IGNORECASE),
     "a count comparison"),
    (re.compile(r"\bno\s+other\b", re.IGNORECASE), "'no other'"),
]

# An exact quantity: absolute only when the test case signs in with a shared
# account (see test_case_problems). "quantity 1", "a quantity of 2", "qty: 3",
# "3 items", "a total of 1500".
_EXACT_QUANTITY = re.compile(
    r"\b(?:quantity|qty)\b(?:\s*(?:of|is|shows?|showing|reads?|set\s+to|at|=|:))*\s*\(?\d"
    r"|\b\d+\s+(?:items?|units?|pieces?|copies)\b"
    r"|\btotal\b(?:\s*(?:of|is|shows?|showing|reads?|=|:))*\s*\D{0,6}\d",
    re.IGNORECASE)

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE = re.compile(r"[;,()]|\s+(?:and|but|while|whereas)\s+", re.IGNORECASE)
# A quoted value: the quote may not sit inside a word, so the apostrophes in
# "the user's cart ... the shopper's list" never pair up into a fake name.
_QUOTED = re.compile(r"(?<![A-Za-z])['\"\u2018\u2019\u201c\u201d]([^'\"\u2018\u2019\u201c\u201d]{2,}?)"
                     r"['\"\u2018\u2019\u201c\u201d](?![A-Za-z])")


def _named_entries(tc) -> set[str]:
    """The entries this test case names: every quoted value in its text and
    every string in its test data. A claim about one of them is about what this
    test did - never about the page as a whole."""
    names = {m.group(1).strip().lower() for t in _texts(tc) for m in _QUOTED.finditer(t)}
    data = getattr(tc, "test_data", None)
    if isinstance(data, dict):
        names |= {str(v).strip().lower() for v in data.values()
                  if isinstance(v, (str, int, float)) and len(str(v).strip()) >= 2}
    return {n for n in names if n}


def _absence_of_a_named_entry(sentence: str, match: re.Match, names: set[str]) -> bool:
    """True when "no row(s)" sits in a clause that names one of the test's
    entries: the relative absence the remedy asks for ("what it removed is
    gone"), whatever the word order. Without a named entry the clause is about
    the page's rows as a whole, which a page that keeps its state cannot promise."""
    start = 0
    for cut in _CLAUSE.finditer(sentence):
        if cut.start() >= match.end():
            break
        if cut.end() <= match.start():
            start = cut.end()
    nxt = _CLAUSE.search(sentence, match.end())
    clause = sentence[start:nxt.start() if nxt else len(sentence)].lower()
    return bool(_QUOTED.search(clause)) or any(n in clause for n in names)


def persistent_pages(inventory: dict) -> dict[str, list[str]]:
    """{page: [words that name it in prose]} for every persistent_state page.

    A page is named by its key (`saved_items` also as `saved items`) and by its
    URL path, so "the saved items" and "/saved_items" both count as mentioning it.
    """
    out: dict[str, list[str]] = {}
    for name, spec in ((inventory or {}).get("pages") or {}).items():
        if not isinstance(spec, dict) or not spec.get("persistent_state"):
            continue
        aliases = {name.lower(), name.lower().replace("_", " ")}
        url = str(spec.get("url") or "")
        if url.startswith("/") and "{" not in url and "<" not in url and len(url) > 1:
            aliases.add(url.lower())
            aliases.add(url.lower().strip("/"))
        out[name] = sorted(a for a in aliases if a)
    return out


def load_persistent_pages() -> dict[str, list[str]]:
    """persistent_pages() of the configured inventory; {} when it cannot be read.

    Fail-soft: without an inventory the dependency rules still apply, only the
    persistent-state rule has nothing to check against.
    """
    import json
    import logging

    from core.app_context import AppContext
    try:
        path = AppContext.load().inventory_path()
        return persistent_pages(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:  # noqa: BLE001 - a missing inventory must not stop drafting
        logging.getLogger("test_case_rules").warning(
            "Persistent pages unavailable (%s: %s); checking dependencies only.",
            type(e).__name__, e)
        return {}


def shared_accounts(inventory: dict) -> list[str]:
    """The accounts the inventory declares under `test_users`. They are SHARED:
    every run that signs in as one inherits what earlier runs left behind."""
    users = (inventory or {}).get("test_users") or {}
    return sorted(str(k) for k in users) if isinstance(users, dict) else []


def load_shared_accounts() -> list[str]:
    """shared_accounts() of the configured inventory; [] when it cannot be read
    (the signed-in quantity rule then has nothing to check against)."""
    import json
    import logging

    from core.app_context import AppContext
    try:
        path = AppContext.load().inventory_path()
        return shared_accounts(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:  # noqa: BLE001 - a missing inventory must not stop drafting
        logging.getLogger("test_case_rules").warning(
            "Shared accounts unavailable (%s: %s); quantities are not checked.",
            type(e).__name__, e)
        return []


def _signs_in_as(tc, accounts) -> str | None:
    """The shared account this test case signs in with, or None.

    Evidence, not wording: the account's NAME quoted in the text (the way a
    test case names a role - `registered`), or a test-data value equal to it.
    "Shopper is not logged in" names no account, so an anonymous test case is
    never read as signing in."""
    if not accounts:
        return None
    data = getattr(tc, "test_data", None)
    values = ({str(v).strip().lower() for v in data.values() if isinstance(v, (str, int))}
              if isinstance(data, dict) else set())
    texts = _texts(tc)
    for account in accounts:
        low = account.lower()
        if low in values:
            return account
        quoted = re.compile(r"[`'\"\u2018\u2019\u201c\u201d]" + re.escape(low)
                            + r"[`'\"\u2018\u2019\u201c\u201d]", re.IGNORECASE)
        if any(quoted.search(t) for t in texts):
            return account
    return None


def rejection_note(problems: list[str]) -> str:
    """The text appended to the prompt when a draft is sent back."""
    return ("\n\n# Your previous answer was rejected\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\nReturn the complete corrected answer, fixing every problem above.")


def _texts(tc) -> list[str]:
    """Every prose field of a test case, skipping anything that is not text."""
    out = []
    for field in ("description", "expected_outcome"):
        value = getattr(tc, field, None)
        if isinstance(value, str):
            out.append(value)
    pre = getattr(tc, "preconditions", None)
    if isinstance(pre, list):
        out.extend(p for p in pre if isinstance(p, str))
    steps = getattr(tc, "steps", None)
    if isinstance(steps, list):
        for step in steps:
            for field in ("action", "expected_result"):
                value = getattr(step, field, None)
                if isinstance(value, str):
                    out.append(value)
    return out


def _expected_texts(tc) -> list[str]:
    out = []
    value = getattr(tc, "expected_outcome", None)
    if isinstance(value, str):
        out.append(value)
    steps = getattr(tc, "steps", None)
    if isinstance(steps, list):
        out.extend(s.expected_result for s in steps
                   if isinstance(getattr(s, "expected_result", None), str))
    return out


def _mentions(sentence: str, aliases: list[str]) -> bool:
    low = sentence.lower()
    return any(re.search(r"(?<![\w/])" + re.escape(a) + r"(?![\w])", low) for a in aliases)


def _short(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def test_case_problems(tc, persistent: dict[str, list[str]] | None = None,
                       accounts=None) -> list[str]:
    """Why one drafted test case cannot be accepted. Empty when it is fine.

    `accounts` - the shared accounts (load_shared_accounts()). Without them the
    signed-in quantity rule is off, exactly as before it existed."""
    title = getattr(tc, "title", "") if isinstance(getattr(tc, "title", ""), str) else ""
    problems: list[str] = []
    for text in _texts(tc):
        for pattern, why in _DEPENDENCY:
            m = pattern.search(text)
            if m:
                problems.append(
                    f"'{title}': {why} (\"{_short(text)}\"). Every test case runs on its own "
                    f"in a fresh browser session, in any order: create every state it needs "
                    f"in its own steps and never refer to another test case.")
                break
    names = _named_entries(tc)
    account = _signs_in_as(tc, accounts) if persistent else None
    for page, aliases in sorted((persistent or {}).items()):
        for text in _expected_texts(tc):
            for sentence in _SENTENCE.split(text):
                if not sentence.strip() or not _mentions(sentence, aliases):
                    continue
                if account and _EXACT_QUANTITY.search(sentence):
                    problems.append(
                        f"'{title}': states an exact quantity about the {page} page "
                        f"(\"{_short(sentence)}\") while signing in as the shared "
                        f"'{account}' account. That page keeps its state against the "
                        f"account between runs, so a run that stopped before cleaning up "
                        f"leaves the same entry there and the quantity read is not what "
                        f"this test added - the code-generation gate refuses it. Either "
                        f"state only that the entry this test added is present (or that "
                        f"what it removed is gone), without a number; or, if this test "
                        f"does not need an account, do not sign in - a fresh session "
                        f"starts empty and may state a quantity.")
                for pattern, what in _ABSOLUTE:
                    m = pattern.search(sentence)
                    if m and pattern is _NONE_PATTERN and _absence_of_a_named_entry(
                            sentence, m, names):
                        continue
                    if m:
                        problems.append(
                            f"'{title}': states {what} about the {page} page (\"{_short(sentence)}\"). "
                            f"That page keeps its state between runs, so an absolute count or "
                            f"emptiness cannot be relied on. State the outcome relative to what "
                            f"this test did: what it added is present, or what it removed is gone "
                            f"(for example: \"no row for '<item>' is present\").")
                        break
    return list(dict.fromkeys(problems))


def draft_problems(test_cases, persistent: dict[str, list[str]] | None = None,
                   accounts=None) -> list[str]:
    """Every problem across a drafted set, in order."""
    out: list[str] = []
    for tc in test_cases or []:
        out.extend(test_case_problems(tc, persistent, accounts))
    return out
