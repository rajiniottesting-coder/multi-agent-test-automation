"""Every acceptance criterion needs a test that can FAIL if it is not met.

WHAT WENT WRONG (validation story: "remove a field")
    A story removed a field from a page. Agent 1 revised the tests that had used
    the field, so they stopped touching it, and drafted one new test for the
    other new behaviour. Nothing asserted that the field is GONE. Every test
    passed against an application that still had the field: green, and proving
    nothing about the story's first criterion.

    The cause is structural, not a wording slip. Agent 1 was told to add a new
    test "only for criteria no revised test covers", but nothing made it say
    which criterion each test covers, and nothing checked the answer. A removal
    is the easiest criterion to skip: once the old tests stop using the thing,
    they all look as if they already cover the story.

THE RULE, FOR ANY STORY
    1. The story's acceptance criteria are read from the story text itself,
       deterministically, and numbered AC1, AC2, ... The model is not trusted to
       list them: a criterion it forgets would never be checked.
    2. Agent 1 answers with a coverage map: for each criterion, the test
       case(s) of THIS answer that verify it. A criterion with no entry, or an
       entry citing a test that is not in the answer, rejects the draft.
    3. Some criteria can only be verified by watching something NOT happen,
       and each gets an obligation the covering test must meet:

       REMOVED   something is removed, replaced, renamed, hidden, disabled, "no
                 longer" offered or "no X is shown": a step whose expected
                 result states the OLD thing is absent, naming it.
       RESTRICTED only X can / Y cannot / must not: a step showing the refusal.
       RULE      a limit or validation rule (at most N, required, valid format):
                 a step showing a value that breaks the rule is rejected.

       A test that merely stopped using the removed thing, or only exercises
       the happy path of a rule, passes whether or not the story was built.

    The same rules apply in normal mode and in impact-aware mode, where a revised
    test case counts only if it carries such a step, and an existing scenario may
    be cited only for a criterion with no obligation (its steps cannot be read
    here, so it cannot prove one).

    What a step must say is decided by validators.absence_claims - the same
    module Agent 2 uses to carry that step into the scenario, so what Agent 1
    accepts as proof is exactly what Agent 2 must keep.

Generic on purpose: the vocabulary is plain English about requirements, and the
only application-specific input is the story text, so nothing here names an
application.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from validators.absence_claims import states_absence, states_exclusion, states_refusal

STRICT = "strict"      # removed / replaced / hidden / not offered: needs an ABSENCE step
LENIENT = "lenient"    # restricted / refused: needs a refusal or absence step
RULE = "rule"          # limit or validation rule: needs a step showing the violation rejected


@dataclass(frozen=True)
class Criterion:
    """One thing the story requires.

    mapped: True when the coverage map must list it by ref (every parsed
    acceptance criterion). False for a requirement found only in the title or
    description: it is checked against the whole draft instead, because the
    model was never shown a ref to cite for it.
    """
    ref: str
    text: str
    source: str
    obligation: str | None
    mapped: bool


# ─────────────────────────────────────────────────────────────
# Which criteria carry an obligation
# ─────────────────────────────────────────────────────────────
_REMOVAL = re.compile(r"""
      \bno\s+longer\b
    | \b(?:remov(?:e|es|ed|ing|al)|delet(?:e|es|ed|ing|ion)|retir(?:e|es|ed|ing)
        |deprecat\w+|discontinu\w+|eliminat\w+|replac(?:e|es|ed|ing|ement)
        |renam(?:e|es|ed|ing)|disabl(?:e|es|ed|ing)|hid(?:e|es|ing)|hidden)\b
    | \bdrop(?:s|ped|ping)?\b(?!-)
    | \binstead\s+of\b
    | \bget(?:s)?\s+rid\s+of\b
    | (?:\bnot|n't)\s+(?:be\s+)?(?:offer(?:ed|s)?|show(?:n|s)?|display(?:ed|s)?|visible
        |available|present|listed|accessible)\b
    | \bdoes(?:\s+not|n't)\s+(?:offer|show|display|have|include|contain|list|provide|support)\b
    | \bno\s+(?:[\w'\-]+\s+){0,4}?(?:is|are)\s+(?:shown|displayed|offered|visible|present
        |available|listed|opened|appears?)\b
    | \bwithout\s+(?:a|an|the|any)\b
""", re.IGNORECASE | re.VERBOSE)

_RESTRICTION = re.compile(r"""
      \bonly\b[^.;\n]{0,60}\b(?:can|may|are\s+allowed|is\s+allowed)\b
    | \b(?:cannot|can't|can\s+not|unable\s+to|must\s+not|should\s+not|may\s+not
        |mustn't|shouldn't)\b
    | \bnot\s+(?:allowed|permitted)\b
    | \b(?:forbidden|prohibited|restricted\s+to|read-only)\b
""", re.IGNORECASE | re.VERBOSE)

_RULE = re.compile(r"""
      \b(?:at\s+(?:most|least)|maximum|minimum|up\s+to|no\s+(?:more|fewer|less)\s+than
        |(?:more|fewer|less)\s+than|exceed(?:s|ed|ing)?|limit(?:ed|s)?\s+(?:to|of))\b
    | \bbetween\s+\d[\d,.]*\s+and\s+\d
    | \b\d[\d,.]*\s*(?:characters?|chars|digits?|letters?|attempts?|tries|minutes?|seconds?
        |hours?|days?|decimal\s+places)\b
    | \b(?:required|mandatory|invalid|valid\s+(?:email|format|date|number|phone|address)
        |must\s+be\s+(?:a\s+)?valid|in\s+the\s+format)\b
""", re.IGNORECASE | re.VERBOSE)


# Who may do something: "only librarians can delete a book" restricts the
# deleting, it does not delete anything - so it outranks a removal word.
_WHO_MAY = re.compile(r"""
      \bonly\b[^.;\n]{0,60}\b(?:can|may|are\s+allowed|is\s+allowed)\b
    | \b(?:cannot|can't|can\s+not|unable\s+to)\b
    | \bnot\s+(?:allowed|permitted)\b
    | \b(?:forbidden|prohibited|restricted\s+to|read-only)\b
""", re.IGNORECASE | re.VERBOSE)


def obligation(text: str, explicit: bool = True) -> str | None:
    """STRICT, LENIENT, RULE or None for one requirement's wording.

    A restriction or a rule is only checked for an explicit acceptance
    criterion: in free description prose "cannot" or "at least" is too common
    to demand a test of it.
    """
    if explicit and _WHO_MAY.search(text or ""):
        return LENIENT
    if _REMOVAL.search(text or ""):
        return STRICT
    if explicit and _RESTRICTION.search(text or ""):
        return LENIENT
    if explicit and _RULE.search(text or ""):
        return RULE
    return None


# ─────────────────────────────────────────────────────────────
# Reading the criteria out of the story
# ─────────────────────────────────────────────────────────────
_HEADING = re.compile(r"^(?:acceptance\s+criteri(?:a|on)\b\s*[:\-–—]?|acs?\s*:)\s*(.*)$",
                      re.IGNORECASE)
# Jira hands the agents WIKI markup ("h3. ", "* bullet", "# numbered", "*bold*");
# the Atlassian connector hands back markdown. Both are read.
_ITEM = re.compile(r"^(\s*)((?:AC\s*)?\d+\s*[.:)]|[-*•]+)\s+(.+)$", re.IGNORECASE)
_HASH_ITEM = re.compile(r"^(\s*)(#+)\s+(.+)$")
_GHERKIN_START = re.compile(r"^\s*(?:given|scenario)\b", re.IGNORECASE)
_GHERKIN_CONT = re.compile(r"^\s*(?:when|then|and|but)\b", re.IGNORECASE)
_SECTION = re.compile(r"^\s*(?:#{1,6}\s|h[1-6]\.\s|\*[^*\s][^*]*\*:?\s*$|\*\*[^*]+\*\*:?\s*$"
                      r"|__[^_]+__:?\s*$)")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def _plain(text: str) -> str:
    """Strip markup (markdown and Jira wiki): emphasis, code, links, colour."""
    text = re.sub(r"\[([^\]|]+)\|[^\]]*\]", r"\1", text)          # [text|url]
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)          # [text](url)
    text = re.sub(r"\{\{([^}]*)\}\}", r"\1", text)                 # {{code}}
    text = re.sub(r"\{color[^}]*\}", "", text)
    text = re.sub(r"^\[[ xX]\]\s*", "", text.strip())               # checklist box
    text = re.sub(r"[*`]+", "", text)
    text = re.sub(r"(?<!\w)_+|_+(?!\w)", "", text)
    return " ".join(text.split())


def _heading_rest(line: str) -> str | None:
    """The text after an 'Acceptance criteria' heading, or None if not one."""
    bare = re.sub(r"^(?:h[1-6]\.\s*)?", "", line.strip())
    bare = re.sub(r"^[#>*_\s]+", "", bare)
    bare = re.sub(r"[*_]+", "", bare)
    m = _HEADING.match(bare.strip())
    if not m:
        return None
    return m.group(1).strip(" :-")


def parse_acceptance_criteria(description: str | None) -> list[str]:
    """The items listed under an 'Acceptance criteria' heading, in order.

    Numbered, bulleted, checklist and Given/When/Then items are understood, in
    Jira wiki markup and in markdown; a wrapped line continues the item above
    it; the list ends at the next heading or at a paragraph after a blank line.
    [] when there is no such heading.
    """
    items: list[str] = []
    in_list = False
    blank = False
    hash_items: bool | None = None       # does THIS list number its items with '#'?
    for raw in (description or "").splitlines():
        line = raw.rstrip()
        if not in_list:
            rest = _heading_rest(line)
            if rest is not None:
                in_list = True
                if len(rest) > 3:
                    items.append(_plain(rest))
            continue
        if not line.strip():
            blank = True
            continue
        item = _ITEM.match(line)
        if item:
            hash_items = False if hash_items is None else hash_items
        else:
            hashed = _HASH_ITEM.match(line)
            if hashed and (hash_items or (hash_items is None and not items)):
                item, hash_items = hashed, True
        if item:
            indent, marker, text = item.groups()
            nested = len(indent.expandtabs(2)) >= 2 or (len(marker) > 1 and not marker[0].isalnum())
            if nested and items:        # a sub-point belongs to the criterion above it
                items[-1] = f"{items[-1]}; {_plain(text)}"
            else:
                items.append(_plain(text))
            blank = False
            continue
        if _GHERKIN_START.match(line):
            items.append(_plain(line))
            blank = False
            continue
        if items and _GHERKIN_CONT.match(line):
            items[-1] = f"{items[-1]} {_plain(line)}"
            blank = False
            continue
        if items and (_SECTION.match(line) or blank):
            break
        if items:
            items[-1] = f"{items[-1]} {_plain(line)}"
        else:
            items.append(_plain(line))
        blank = False
    return [i for i in items if i]


def extract_criteria(title: str | None, description: str | None) -> list[Criterion]:
    """Every requirement Agent 1's draft is held to, for one story.

    With an acceptance-criteria list: each item, as AC1..ACn, mapped; plus the
    title when IT announces a removal that no item does. Without one: the title
    and any description sentence that announces a removal, checked against the
    draft as a whole.
    """
    title = _plain(title or "")
    items = parse_acceptance_criteria(description)
    found: list[Criterion] = []
    if items:
        for n, text in enumerate(items, 1):
            found.append(Criterion(f"AC{n}", text, "acceptance criteria",
                                   obligation(text), True))
        if title and not any(c.obligation == STRICT for c in found) \
                and obligation(title, explicit=False) == STRICT:
            found.append(Criterion("TITLE", title, "title", STRICT, False))
        return found
    if title and obligation(title, explicit=False) == STRICT:
        found.append(Criterion("TITLE", title, "title", STRICT, False))
    n = 0
    for sentence in _SENTENCE.split(_plain_lines(description)):
        sentence = sentence.strip()
        if sentence and obligation(sentence, explicit=False) == STRICT:
            n += 1
            found.append(Criterion(f"S{n}", sentence, "description", STRICT, False))
    return found


def _plain_lines(text: str | None) -> str:
    return "\n".join(_plain(line) for line in (text or "").splitlines())


# ─────────────────────────────────────────────────────────────
# Which steps prove an obligation, and that they are about the right thing
# ─────────────────────────────────────────────────────────────
_STOP = frozenset("""about above after again against also been before being below between both
could does doing down during each every from further have having here into just more most must
much only other over same should shall some such than that their them then there these they this
those through under until upon very were what when where which while will with would your""".split())
# Words that say nothing about WHICH thing was removed.
_GENERIC = frozenset("""page pages user users shopper shoppers customer customers visitor visitors
screen screens field fields option options button buttons control controls link links section
sections item items offer offers offered offering show shows shown display displays displayed
longer exactly instead without present available visible removed remove hidden""".split())
_QUOTED_VALUE = re.compile(r"(?<![A-Za-z])['\"‘’“”][^'\"‘’“”]{2,}"
                           r"['\"‘’“”](?![A-Za-z])")
_WORD = re.compile(r"[a-z0-9][a-z0-9'\-]*")
_OBJECT_END = re.compile(r"[.;,:()]|\s(?:from|on|in|at|when|while|so|because|and|but|for|to|by"
                         r"|after|before|unless|if|anymore|any\s+more)\s", re.IGNORECASE)
_SUBJECT_START = re.compile(r"[.;,:()]|\s(?:and|but|so|when|while|then)\s", re.IGNORECASE)


def _words(text: str) -> dict:
    """{stem: word} for the distinctive words of a text. The stem is the first
    five letters, so 'choice'/'choices' and 'quantity'/'quantities' compare equal."""
    out: dict = {}
    for tok in _WORD.findall((text or "").lower()):
        tok = tok.strip("'-")
        if (len(tok) >= 4 and tok not in _STOP and tok not in _GENERIC
                and not _REMOVAL.fullmatch(tok)):
            out.setdefault(tok[:5], tok)
    return out


def removed_object(text: str) -> dict:
    """{stem: word} naming WHAT the criterion removes.

    The words right after the removal cue ("no longer offers a quantity field"
    -> quantity), or inside it ("no confirmation pop-up is shown"), or - for a
    passive sentence - the words before it ("a product can be removed" ->
    product). Falls back to the whole criterion.
    """
    m = _REMOVAL.search(text or "")
    if not m:
        return _words(text)
    rest = text[m.end():]
    quoted = _QUOTED_VALUE.match(rest.lstrip())
    if quoted:                                   # instead of "Old wording": the wording is the thing
        found = _words(quoted.group(0))
        if found:
            return found
    cut = _OBJECT_END.search(" " + rest + " ")
    after = (" " + rest + " ")[:cut.start()] if cut else rest
    found = _words(m.group(0) + " " + after)
    if found:
        return found
    before = text[:m.start()]
    parts = _SUBJECT_START.split(" " + before + " ")
    found = _words(parts[-1] if parts else before)
    return found or _words(text)


def _steps(tc) -> list[tuple[str, str]]:
    out = []
    for step in getattr(tc, "steps", None) or []:
        action = getattr(step, "action", "")
        expected = getattr(step, "expected_result", "")
        if isinstance(action, str) and isinstance(expected, str):
            out.append((action, expected))
    return out



def _names_an_entry(text: str, tc) -> bool:
    """Does the text name a concrete entry - a quoted value, or a value of the
    test case's test data? "No row for '<the item>' is present" names the item a
    deletion removed even though it never says the criterion's noun."""
    if _QUOTED_VALUE.search(text or ""):
        return True
    data = getattr(tc, "test_data", None) or {}
    low = (text or "").lower()
    return isinstance(data, dict) and any(
        isinstance(v, (str, int, float)) and len(str(v).strip()) >= 3
        and str(v).strip().lower() in low for v in data.values())


def evidence_steps(tc, tier: str) -> list[str]:
    """Texts (action + expected result) of the steps that can prove the tier.

    Judged on the EXPECTED result only: the action is what the tester does,
    the expected result is what is asserted. STRICT needs absence (or, for a
    removed page, that it cannot be reached); LENIENT and RULE accept a refusal
    or an absence."""
    if tc is None:
        return []
    out = []
    for action, expected in _steps(tc):
        if tier == STRICT:
            hit = states_exclusion(expected)
        else:
            hit = states_refusal(expected) or states_exclusion(expected)
        if hit:
            out.append(f"{action} {expected}")
    return out


# ─────────────────────────────────────────────────────────────
# Citing test cases
# ─────────────────────────────────────────────────────────────
_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
EXISTING = "existing scenario"


def _norm_title(title: str) -> str:
    title = re.sub(r"^\s*(?:\[[^\]]*\]\s*)+", "", title or "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", title.lower()).split())


class CaseIndex:
    """The test cases of ONE answer, findable by revised key or by title, plus
    (impact-aware mode) the titles of scenarios that already exist."""

    def __init__(self, revisions=(), new=(), existing=()):
        self.by_key: dict = {}
        self.by_title: dict = {}
        self.existing: dict = {}
        self.labels: list[str] = []
        for key, tc in revisions:
            self.by_key[key] = tc
            self.by_title.setdefault(_norm_title(getattr(tc, "title", "")), (key, tc))
            self.labels.append(f"{key} ({getattr(tc, 'title', '')})")
        for tc in new:
            title = getattr(tc, "title", "")
            self.by_title.setdefault(_norm_title(title), (title, tc))
            self.labels.append(title)
        for title in existing:
            norm = _norm_title(title)
            if norm and norm not in self.by_title:
                self.existing[norm] = title

    @property
    def cases(self) -> list:
        seen, out = set(), []
        for _id, tc in list(self.by_key.items()) + list(self.by_title.values()):
            if id(tc) not in seen:
                seen.add(id(tc))
                out.append((_id, tc))
        return out

    def resolve(self, cited: str):
        """(id, test case) for a cited key or title; (title, None) for an
        existing scenario; None when nothing matches."""
        text = cited or ""
        for key in _KEY.findall(text):
            if key in self.by_key:
                return key, self.by_key[key]
        norm = _norm_title(text)
        hit = self.by_title.get(norm)
        if hit:
            return hit
        if norm in self.existing:
            return f"{EXISTING} '{self.existing[norm]}'", None
        return None


def index_cases(revisions=(), new=(), existing=()) -> CaseIndex:
    """revisions: [(key, TestCase)], new: [TestCase], existing: [scenario title]."""
    return CaseIndex(revisions, new, existing)


# ─────────────────────────────────────────────────────────────
# The check
# ─────────────────────────────────────────────────────────────
def _ref(text: str) -> str:
    """The criterion number a map entry names: '1', 'AC1' and 'AC1: ...' are one."""
    t = (text or "").strip()
    m = re.match(r"(?:AC\s*)?(\d+)\b", t, re.IGNORECASE)
    if m:
        return f"AC{m.group(1)}"
    m = re.match(r"(TITLE|S\d+|C\d+)\b", t, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return " ".join(t.lower().split())


def _short(text: str, limit: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


_NEED = {
    STRICT: ("says something is removed, replaced, renamed, hidden or no longer offered, so a "
             "test must OBSERVE that it is gone: a step whose expected result states the "
             "absence (for example \"<the removed thing> is not present on <the place it used "
             "to be>\"), naming what was removed in the story's own words"),
    LENIENT: ("restricts what is allowed, so a test must show the refusal: a step whose "
              "expected result states the action is denied, rejected or not offered"),
    RULE: ("states a limit or a validation rule, so a test must show BOTH sides: a value that "
           "keeps the rule is accepted, and one that breaks it - just past the limit, empty "
           "where it is required, malformed - is rejected, in a step whose expected result "
           "states the rejection or the error"),
}


def _gap(ref: str, text: str, tier: str, cases: list, why: str) -> str:
    titles = ", ".join(f"'{_short(getattr(tc, 'title', '') or i, 60)}'" for i, tc in cases) or "none"
    return (f"{ref} (\"{_short(text)}\") {_NEED[tier]}. {why} Covering test case(s): {titles}. A "
            f"test that never watches this happen passes whether or not the story was built. "
            f"Add such a step to a test case of this answer that already visits that place, or "
            f"draft a test case for it.")


def _obligation_problem(ref: str, text: str, tier: str, cases: list) -> str | None:
    if cases and all(tc is None for _i, tc in cases):
        return _gap(ref, text, tier, cases,
                    "Only existing scenarios are cited, and an existing scenario cannot prove "
                    "something this story changes.")
    evidence = [(t, tc) for _id, tc in cases for t in evidence_steps(tc, tier)]
    if not evidence:
        return _gap(ref, text, tier, cases, "None of them has such a step.")
    if tier == STRICT:
        thing = removed_object(text)
        whole = _words(text)
        about = [t for t, tc in evidence
                 if set(thing) & set(_words(t))
                 or (set(whole) & set(_words(t)) and _names_an_entry(t, tc))]
        if thing and not about:
            return _gap(ref, text, tier, cases,
                        "Their absence steps are about something else - name what was "
                        "removed (the criterion speaks of: " + ", ".join(sorted(thing.values()))
                        + ").")
    return None


def coverage_problems(criteria, coverage, index: CaseIndex) -> list[str]:
    """Why a draft's coverage map cannot be accepted. [] when it is fine.

    criteria: extract_criteria() of the story. coverage: the draft's
    CriterionCoverage entries. index: the draft's test cases. A story with no
    parsed criteria and an empty map is accepted unchanged, as before.
    """
    problems: list[str] = []
    entries: dict = {}
    for entry in list(coverage or []):
        entries.setdefault(_ref(getattr(entry, "criterion", "") or ""), []).append(entry)
    listed = ", ".join(index.labels) or "(none)"
    if index.existing:
        listed += " - or an existing scenario by its title as listed"

    def cited_cases(ref: str) -> list:
        cases, bad = [], []
        for entry in entries.get(ref, []):
            for cite in getattr(entry, "covered_by", None) or []:
                hit = index.resolve(cite)
                (cases if hit else bad).append(hit or cite)
        for cite in bad:
            problems.append(f"coverage for {ref} cites '{_short(str(cite), 80)}', which is not a "
                            f"test case in this answer. Cite a title or key from: {listed}.")
        return cases

    known = set()
    for c in criteria or []:
        known.add(c.ref)
        cases = cited_cases(c.ref)
        if c.mapped and not entries.get(c.ref):
            problems.append(f"{c.ref} (\"{_short(c.text)}\") is not in the coverage map. List every "
                            f"acceptance criterion with the test case(s) that verify it.")
            continue
        if c.mapped and not cases:
            if entries.get(c.ref):
                problems.append(f"{c.ref} (\"{_short(c.text)}\") cites no test case that exists in "
                                f"this answer. Cite a title or key from: {listed}.")
            continue
        if c.obligation:
            pool = cases if c.mapped else index.cases
            problem = _obligation_problem(c.ref, c.text, c.obligation, pool)
            if problem:
                problems.append(problem)

    for ref, group in entries.items():
        if ref in known:
            continue
        cases = cited_cases(ref)
        for entry in group:
            text = getattr(entry, "criterion", "") or ""
            tier = obligation(text)
            if tier and cases:
                problem = _obligation_problem(ref, text, tier, cases)
                if problem:
                    problems.append(problem)
    return list(dict.fromkeys(problems))


# ─────────────────────────────────────────────────────────────
# Showing it
# ─────────────────────────────────────────────────────────────
_NOTE = {
    STRICT: ("  <- something is REMOVED, REPLACED or NOT OFFERED: a step must assert it is "
             "ABSENT, naming it"),
    LENIENT: "  <- a RESTRICTION: a step must show the refusal",
    RULE: ("  <- a LIMIT or RULE: a step must show a value breaking it is REJECTED (and one "
           "keeping it accepted)"),
}


def criteria_block(criteria) -> str:
    """The numbered criteria as the prompt shows them to the model."""
    if not criteria:
        return ("(No acceptance-criteria list was found in the story. Derive the criteria from "
                "the story yourself and list each in `coverage`, numbered C1, C2, ...)")
    lines = []
    for c in criteria:
        note = _NOTE.get(c.obligation, "")
        where = "" if c.mapped else f" (from the story {c.source}; some test case must assert it)"
        lines.append(f"- {c.ref}: {c.text}{where}{note}")
    return "\n".join(lines)


def render_coverage(criteria, coverage, index: CaseIndex) -> list[str]:
    """Lines for a Jira comment: each criterion and what verifies it."""
    wording = {c.ref: c.text for c in criteria or []}
    lines = []
    for entry in coverage or []:
        ref = _ref(getattr(entry, "criterion", "") or "")
        text = wording.get(ref) or getattr(entry, "criterion", "")
        cited = []
        for cite in getattr(entry, "covered_by", None) or []:
            hit = index.resolve(cite)
            cited.append(hit[0] if hit else cite)
        how = getattr(entry, "how_verified", "") or ""
        lines.append(f"- {ref} {_short(text, 140)} -> {', '.join(cited) or '(none)'}"
                     + (f" | {_short(how, 140)}" if how else ""))
    return lines
