"""
Turn a raw test failure into a plain-English CAUSE and REMEDY.

WHY THIS EXISTS
    A Playwright failure names what the framework was doing, never what was
    wrong with the application. "strict mode violation: resolved to 3
    elements", "Timeout 30000ms exceeded", `assert '' == 'qa_user_123'` - each
    of those took a person with the whole repo in their head, a trace file and
    a browser to interpret. Every one of them has a small number of causes and
    a specific remedy, and nothing was writing them down.

    So each failure now carries three lines in the log and the job summary:

        WHAT   the raw error, unchanged
        CAUSE  what this class of error actually means
        FIX    the concrete next action, naming the helper or the file

DESIGN NOTES
    - Signature matching is ORDERED, most specific first. A strict-mode
      violation is also a timeout in some phrasings; the specific reading wins.
    - Unknown failures get a generic entry rather than nothing. Silence is the
      thing being fixed; a vague hint still beats a bare traceback.
    - APP-AGNOSTIC. Signatures are Playwright's and pytest's, remedies name
      BasePage helpers and framework files. No application, page or element
      name appears here - onboarding a different app changes nothing in this
      module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnosis:
    """A human-readable reading of one failure."""
    label: str      # short name for the failure class
    cause: str      # what it means
    remedy: str     # what to do about it

    def as_lines(self, indent: str = "") -> list[str]:
        return [
            f"{indent}CAUSE ({self.label}): {self.cause}",
            f"{indent}FIX:   {self.remedy}",
        ]


# (compiled pattern, Diagnosis) - ORDER MATTERS, most specific first.
_SIGNATURES: list[tuple[re.Pattern, Diagnosis]] = [
    (
        re.compile(r"strict mode violation.*resolved to (\d+) elements", re.I),
        Diagnosis(
            "multi-match selector",
            "The selector matches SEVERAL elements. Playwright runs strict, so "
            "click / fill / wait / assert all raise rather than guessing which "
            "one you meant.",
            "Check the page's `multi_match` list in the app inventory. Read the "
            "whole set with get_all_texts / get_count, or select ONE member by "
            "its text (select_custom_option, click_role) or via a `<key>_first` "
            "key. Never build a narrowed selector by hand.",
        ),
    ),
    (
        # `Expected <short>, got <much longer text CONTAINING it>`.
        #
        # The expected value is INSIDE the actual - the signature of
        # comparing a field against the container it lives in. A reader
        # named for one cell returned the whole row, and the equality could
        # not hold on any data. It arrived from CI as "unclassified", so the
        # generic reading sent the reader to the trace viewer, where the
        # page is perfectly healthy and the value is right there in the row.
        #
        # Placed BEFORE the empty-value check deliberately: that one needs
        # `got ''` so the two cannot overlap, and this must not fall through
        # to the membership reading, whose remedy is to wait.
        re.compile(
            r"expected\s+.{0,40}?['\"](?P<want>[^'\"]{1,40})['\"].{0,60}?"
            r"got\s+['\"](?P<got>[^'\"]{60,})['\"]",
            re.I | re.S,
        ),
        Diagnosis(
            "field compared against its container",
            "A short expected value was compared against a much longer "
            "string that appears to CONTAIN it. That is what happens when a "
            "reader returns the whole row - every cell concatenated - and "
            "the assertion wants one cell from it. The equality cannot hold "
            "on any data, in any run, so the page is fine and the test could "
            "never have passed. Read the actual value in the message: if the "
            "expected value is visible inside it, this is the cause.",
            "Read the CELL, not the row. BasePage.get_cell_text(<row "
            "family>, row_index, cell_index) addresses one cell, and "
            "find_row_index_by_text() locates the row first; "
            "get_column_values(<row family>, <cell selector>) reads one "
            "column across every row. Rename the page-object method if it "
            "promised a field and returned a row. If the inventory describes "
            "no cell for that value it is not readable on this page - assert "
            "something the page can actually show.",
        ),
    ),
    (
        re.compile(r"assert\s+''\s*==|Expected.*got ''|== ''", re.I),
        Diagnosis(
            "element found but empty",
            "The locator RESOLVED - the failure is not a missing element - but "
            "the text it read was empty. Usually an off-by-one into a "
            "neighbouring cell, or a read that beat an async re-render.",
            "Check the column index if this is a table cell (a leading checkbox "
            "or icon column shifts every index by one), and confirm the value "
            "has rendered before reading - wait_for_text() rather than reading "
            "and comparing.",
        ),
    ),
    (
        # An action waited for an element that only exists on ANOTHER page,
        # which almost always means the navigation that should have taken us
        # there did not happen. The commonest cause on an ad-supported site is
        # an interstitial: Google's Vignette consumes the first navigation
        # after a page load, parks the address on `#google_vignette`, and lets
        # the click through only once it is dismissed.
        #
        # The evidence is deceptive. By the time the failure screenshot is
        # taken the ad has gone and the destination looks perfectly healthy -
        # a trace showed a nav click at +3.7s, the next action waiting the full
        # 30s, and a screenshot at +34.9s of the page it had been waiting for.
        # Only when the log shows a wait that NEVER resolved. A log containing
        # "locator resolved to" is the hidden case below, whose remedy is the
        # opposite - my first version of this pattern matched both and stole
        # it, which is the same mistake in reverse.
        re.compile(
            r"(?s)\A(?!.*locator resolved to).*"
            # `locator(` belongs here too, and its absence cost a session.
            #
            # self.sel() yields a CSS or attribute selector for most elements,
            # so the log reads `waiting for locator("[data-qa='...']")` rather
            # than any get_by_* form. Those fell through to the generic
            # "timed out" reading, whose advice is the OPPOSITE of the truth:
            # it says the element is present but not actionable, when a wait
            # that never resolved means there were ZERO matches.
            #
            # Safe to add because the discriminator is the negative lookahead
            # above, not the engine name: a log carrying "locator resolved to"
            # is the hidden case and is excluded before this ever runs.
            r"waiting for (?:locator|get_by_placeholder|get_by_label"
            r"|get_by_alt_text|get_by_title|get_by_role|get_by_text)",
            re.I),
        Diagnosis(
            "element never appeared - probably the wrong page",
            "The wait never resolved at all: no 'locator resolved to' line "
            "means zero matches, not a hidden or blocked element. The element "
            "is almost certainly on a page the browser never reached.",
            "Compare the action timeline in the trace: if a navigation happened "
            "shortly before this wait, check whether it actually landed. An ad "
            "INTERSTITIAL is the usual culprit - it swallows the first "
            "navigation after a page load and parks the URL on a fragment such "
            "as #google_vignette, so the click appears to work and nothing "
            "moves. The failure screenshot is taken after the ad has gone, so "
            "it shows the destination looking healthy and proves nothing. "
            "BasePage.dismiss_interstitial() clears one; a step that navigates "
            "should confirm the destination is ready before the next step acts "
            "on it.",
        ),
    ),
    (
        # PRESENT BUT HIDDEN, and the page recorded failed requests. wait_visible
        # appends them (pages/base_page.py, watch_network). The likeliest reading
        # is then that the application refused or never answered the action,
        # not that the scenario assumed a wrong starting state - so this more
        # specific entry is tried first.
        re.compile(r"PRESENT in the DOM but HIDDEN.*Requests on this page that failed",
                   re.I | re.S),
        Diagnosis(
            "action's request failed",
            "The element is in the DOM but was never shown, and requests on the "
            "page failed or returned an HTTP error while the step waited. The "
            "application did not complete the action, so the state it would "
            "have shown never came about.",
            "Read the failed requests listed in the message. If the action's "
            "own request is among them (an HTTP 5xx, a 429, or no response), "
            "the application or the network refused it: re-run, and if it "
            "keeps failing, check the application under test before the test. "
            "If only unrelated requests failed, treat it as a state problem "
            "and read the trace in reports/failure-evidence/.",
        ),
    ),
    (
        # PRESENT BUT HIDDEN. Playwright says "expected to be visible" for both
        # a missing element and one that is in the DOM and not shown, and the
        # readiness-probe entry below then advises checking the selector. That
        # advice is exactly wrong here: the call log says the locator RESOLVED,
        # so the selector and the page are both right and only the app's STATE
        # is unexpected. This pattern must be tried BEFORE that one.
        re.compile(r"unexpected value \"hidden\"|PRESENT in the DOM but HIDDEN", re.I),
        Diagnosis(
            "element present but hidden",
            "The element IS in the DOM - the call log says the locator "
            "resolved - and the application is simply not showing it. The "
            "selector is right and so is the page; only the STATE is "
            "unexpected.",
            "The selector matched and the page is the right one; the "
            "application is simply not showing the element. Do NOT go looking "
            "at the selector. Look at the step that was supposed to put the "
            "app into this state, and at what the state was BEFORE the "
            "scenario started: anything the application stores against the "
            "signed-in user usually survives logout and survives the run, so "
            "a scenario asserting an absolute state must either register a "
            "fresh account or clear that state first. The trace in "
            "reports/failure-evidence/ shows the DOM at the moment of failure "
            "and will confirm it in seconds.",
        ),
    ),
    (
        # The readiness-probe shape. is_showing() swallows the Playwright error
        # by design and returns False, so the assertion reads `assert False` and
        # the real detail lands in a WARNING log line instead of the traceback.
        # Without this the whole class came back "unclassified" - which is the
        # thing this module exists to prevent (1 Aug 2026).
        re.compile(r"is_showing\(|expected to be visible|No session after", re.I),
        Diagnosis(
            "readiness probe returned False",
            "A page-object readiness check waited for an element and never saw "
            "it. The probe logs the selector, the wait it used and the URL at "
            "WARNING level - read that line, not the bare `assert False`. The "
            "URL usually settles it: the RIGHT page means a wrong selector, "
            "the WRONG page means the step before this one did not do what it "
            "claimed.",
            "Check the selector against the live page: "
            "`python -m scripts.verify_locators --page <page> --only-problems`. "
            "If it resolves there, the app never reached this state. Beware "
            "accessible-name selectors in particular: an icon font that renders "
            "from ligature text puts that text into the name, so "
            "role=<x>[name='...'] can silently match nothing.",
        ),
    ),
    (
        re.compile(r"Timeout .*exceeded.*waiting for.*to be visible", re.I | re.S),
        Diagnosis(
            "element never appeared",
            "The element did not become visible within the timeout. Either the "
            "selector is wrong, or the page never reached the state that "
            "renders it - a form refused client-side, or a navigation that "
            "never completed.",
            "Verify the selector against the live page: "
            "`python -m scripts.verify_locators --page <page> --only-problems`. "
            "If it is green there, the app never got to this state - look at "
            "the step BEFORE this one, and at the screenshot in "
            "reports/failure-evidence/.",
        ),
    ),
    (
        re.compile(r"Timeout .*exceeded", re.I),
        Diagnosis(
            "timed out",
            "An action or wait ran out of time. A click that times out usually "
            "means the element is present but not actionable: covered by an "
            "overlay, disabled, or still animating and therefore not stable.",
            "Read the Playwright call log in the traceback - it names the "
            "actual blocker ('element is not stable', 'not enabled', "
            "'intercepts pointer events'). Adjust `browser.timeout` in "
            "config.yaml only after ruling those out.",
        ),
    ),
    (
        # A results-summary line, in whatever nouns the application uses.
        # This pattern named ONE application's exact wording until a sweep
        # found it sitting in core/ - a framework file is the one place
        # that string could never belong.
        re.compile(r"\b\d+\s+(?:results?|records?|items?|rows?|matches)\s+found\b",
                   re.I),
        Diagnosis(
            "result-count assertion",
            "A results-summary assertion failed. Two usual reasons: the summary "
            "is read before the list re-renders, so it still holds the previous "
            "count; or the filter never applied and the count is the unfiltered "
            "total.",
            "Wait for the expected text instead of reading and comparing. If "
            "the number is the FULL list, the filter did not bind - check the "
            "search field was typed into (not filled) and that the page had "
            "finished navigating first. Summary wording is often "
            "grammatically variable for exactly one match.",
        ),
    ),
    (
        # pytest's assertion rewriting, on `assert some_page.is_thing()`:
        #
        #     assert False
        #      +  where False = is_thing()
        #      +    where is_thing = <pages.x_page.XPage object at 0x...>.is_thing
        #
        # A page-object predicate returned False and said NOTHING about why.
        # This arrived unclassified twice, and the second time there was not
        # even a captured log line to widen into - the predicate had been
        # written on is_visible(), which is a zero-wait probe that logs
        # nothing, so the run produced no evidence at all.
        re.compile(
            r"where\s+False\s*=\s*\w+\(\)"
            r".{0,200}?where\s+\w+\s*=\s*<[\w.]*[Pp]age[^>]*>",
            re.S,
        ),
        Diagnosis(
            "silent page-object predicate",
            "A boolean method on a page object returned False. The assertion "
            "records only that, so on its own it says nothing about WHICH "
            "condition failed or why. Two things produce this. The predicate "
            "may be built on a NON-WAITING probe - is_visible() and "
            "get_count() read the DOM once and log nothing - so it raced a "
            "state change that had not finished, most often immediately after "
            "the action that was supposed to cause it. Or the state was never "
            "established at all, because the scenario assumed a starting "
            "point it did not create: anything the application stores against "
            "the signed-in user survives logout and survives the run.",
            "Look at the page object, not the step. If the predicate calls "
            "is_visible() or compares get_count(), rebuild it on the waiting "
            "equivalent - is_showing() or wait_for_count() - which retries "
            "AND logs the reason it gave up, so the next failure explains "
            "itself. If it already waits and still returned False, the state "
            "is genuinely absent: check what was supposed to establish it, "
            "and whether the scenario owns its own starting state.",
        ),
    ),
    (
        # A value was expected among texts the step had already read. THREE
        # spellings, all the same failure:
        #
        #     assert 'X' not in ['X']            a literal list repr
        #     any(v in t for t in texts)         a comprehension over a family
        #     "Expected ... , got ['a', 'b']"    a custom assertion message
        #
        # Only the first was matched, so the other two arrived unclassified -
        # the comprehension form from a real run, where a step asserted a
        # PRICE against a family that only ever yields NAMES. The literal
        # alternative stays case-sensitive: widening the whole pattern with
        # re.I would change the reading of a branch that was already correct,
        # so the two new ones carry their own inline (?i:...) instead.
        re.compile(
            r"assert\s+.{1,80}?\s+(?:not\s+)?in\s+\["
            r"|(?i:\b(?:any|all)\(\s*[\w.\[\]'\"()]+\s+(?:not\s+)?in\s+\w+\s+for\s+)"
            r"|(?i:\bexpected\b.{0,160}?\bgot\s+\[)",
            re.S,
        ),
        Diagnosis(
            "membership assertion",
            "A value was expected in, or expected gone from, a list of texts "
            "the step had already read. Three causes, in the order worth "
            "checking. The list is a SNAPSHOT: reading it straight after the "
            "action that adds or removes the entry returns what was there "
            "before the action finished, which is the usual cause when the "
            "assertion is about something this scenario just did. The second "
            "is starting state - anything the application stores against the "
            "signed-in user survives the run, so an entry a previous run left "
            "behind is in the list too. The third is not a timing or state "
            "problem at all: the expected value may be a DIFFERENT KIND of "
            "thing from what that family holds. Compare the expected value "
            "against the list in the message - if it could not have appeared "
            "there on any data, the step is reading the wrong element and the "
            "assertion could never have passed.",
            "Read the expected value and the list side by side first. If they "
            "are the same kind of thing, wait for the row rather than reading "
            "the list: BasePage.wait_for_row(<row family>, text, "
            "present=False) after a removal, present=True after an addition. "
            "It re-checks until the timeout instead of looking once. If the "
            "entry is still wrong after waiting, it is starting state and no "
            "wait will help - the scenario has to own what it asserts on. If "
            "they are NOT the same kind of thing, no wait and no fixture "
            "helps: find the inventory key on that page whose text carries "
            "the expected value, and if there is none, that value cannot be "
            "asserted on that page.",
        ),
    ),
    (
        # BasePage.click_in_row() when the row family matched nothing with
        # that text. Its own message names the two selector-shaped causes;
        # this adds the one that is not about selectors at all and is the
        # commonest in a multi-step scenario.
        re.compile(r"No row matching .{1,80}? contains ", re.S),
        Diagnosis(
            "row not present in the list",
            "The row family resolved, but no member of it carries that text. "
            "Three causes, in the order worth checking. The list may be "
            "FILTERED: a search earlier in the scenario narrows the listing to "
            "its matches, so a second item the scenario never searched for is "
            "genuinely not on the page - this is the usual cause when the "
            "scenario touches more than one record. The text may differ from "
            "what is rendered - casing, punctuation, a trailing space. Or the "
            "row locator may match the text element rather than the repeating "
            "CONTAINER, in which case no row ever contains anything.",
            "Read the step BEFORE this one. If it searched, filtered or "
            "paginated, the listing no longer holds every record and the "
            "scenario has to reset it - search again for the second item, or "
            "navigate back to the unfiltered listing - before asking for a row "
            "that was never displayed. If nothing narrowed the list, compare "
            "the expected text against the page character for character, then "
            "check the row locator is the container.",
        ),
    ),
    (
        # A page object refusing to act because the browser is elsewhere.
        # Its own message is already specific; what the classifier adds is
        # the CAUSE, which is almost never the step that raised.
        # `.{1,200}?` with DOTALL, because a long URL wraps in the captured
        # output and the two halves of this sentence routinely land on
        # different lines. A pattern that only matched the unwrapped form
        # would classify some runs and not others, which is worse than
        # classifying none.
        re.compile(r"was called while the browser is at\s.{1,200}?,?\s*not on\s",
                   re.S),
        Diagnosis(
            "acted on the wrong page",
            "A page object was asked to act on a page the browser is not "
            "showing. The step that raised is rarely at fault: something "
            "BEFORE it navigated away and nothing brought the browser back. "
            "The commonest cause is a precondition step placed too early - "
            "one that clears or sets up state, navigates to that state's own "
            "page, and leaves the browser there for the step that follows.",
            "Read the scenario's steps in order and find the last one that "
            "navigates. If a precondition step moved the browser, either put "
            "it after the step that needed the original page, or add a step "
            "that returns there. Where the state belongs to a signed-in user, "
            "the precondition has to run AFTER the sign-in anyway - before "
            "it, there is no user whose state it could be.",
        ),
    ),
    (
        # A call that does not fit the method it names. Python raises before
        # the body runs, so nothing touched the browser and the traceback
        # points at the caller rather than at the application.
        re.compile(r"TypeError:.{0,120}?(missing \d+ required positional argument"
                   r"|takes \d+ positional arguments? but \d+ (?:was|were) given)",
                   re.S),
        Diagnosis(
            "call does not match the method signature",
            "A method was called with the wrong number of arguments. This is "
            "not a timing problem, a selector problem or an application "
            "problem: Python refused the call before the method body ran, so "
            "no browser action was attempted and the screenshot shows "
            "whatever was on screen beforehand.",
            "Read the signature named in the traceback and the call above it. "
            "A step definition that needs a value must REQUEST it - pytest "
            "injects any fixture named in the step function's parameters, "
            "`base_url` included - rather than calling without it. If the "
            "argument is not really needed, change the signature instead; a "
            "parameter nothing passes is one nothing should declare.",
        ),
    ),
    (
        # A value used as the wrong KIND of thing. Python raises the moment
        # the line runs, so nothing was waiting and nothing timed out.
        re.compile(r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
                   re.S),
        Diagnosis(
            "value used as the wrong type",
            "A method was called on a value that does not have it. Not a "
            "timing problem, not a selector problem and not the application: "
            "Python raised as soon as the line ran, so no wait was in "
            "progress and the screenshot shows whatever was on screen "
            "beforehand. The usual cause is a reader that returns a LIST of "
            "values - one per row - being used as if it returned a single "
            "one.",
            "Read the type in the message against the helper that produced "
            "the value. BasePage annotates every reader's return type and the "
            "generation prompt shows it: a `-> List[str]` helper needs an "
            "entry picked out of it before a string method will work, and a "
            "`-> str` helper has nothing to index. No wait and no fixture "
            "changes this.",
        ),
    ),
    (
        # `assert 2 == 1` - two integers, no quotes. Almost always a COUNT.
        #
        # Reported "unclassified" until a run removed one of two rows, counted
        # immediately, and got two. Playwright auto-retries a wait; `.count()`
        # does not - it is a snapshot, and a snapshot taken straight after the
        # click that changes it reads the value from before the click.
        re.compile(r"^\s*E?\s*assert\s+\d+\s*==\s*\d+\s*$", re.M),
        Diagnosis(
            "count assertion",
            "Two integers were compared and differed. The number is nearly "
            "always how many elements matched something, and there are two "
            "usual reasons it is wrong. Either it was READ TOO EARLY - "
            "get_count() is a snapshot with no retry, so counting straight "
            "after the action that changes the list returns the value from "
            "before it. Or the page did not start where the scenario assumed: "
            "anything the application stores against the signed-in user "
            "survives the run, so a previous run's leftovers are counted too.",
            "Use BasePage.wait_for_count(locator, expected), which retries "
            "until the timeout instead of reading once. If the number is "
            "still wrong after waiting, it is starting state, not timing: the "
            "scenario has to own what it asserts on - register a fresh "
            "account, or clear the state first, or assert relatively.",
        ),
    ),
    (
        re.compile(r"fixture '([^']+)' not found", re.I),
        Diagnosis(
            "missing fixture",
            "A step definition asked for a fixture that no conftest.py "
            "provides.",
            "Page-object fixtures are auto-registered from pages/*_page.py by "
            "tests/step_defs/conftest.py - check the class name matches the "
            "fixture name in snake_case. Shared data fixtures belong in "
            "conftest.py, not in a step-definition module.",
        ),
    ),
    (
        re.compile(r"StepDefinitionNotFoundError|step definition is not found", re.I),
        Diagnosis(
            "unimplemented step",
            "A Gherkin step in the feature file has no matching step "
            "definition in that feature's own step-def module.",
            "Step definitions are MODULE-SCOPED in pytest-bdd, not global: the "
            "step must exist in the module that calls scenarios() for this "
            "feature, or in a conftest.py. Copying it from another test module "
            "will not work.",
        ),
    ),
    (
        re.compile(r"ModuleNotFoundError|ImportError|cannot import name", re.I),
        Diagnosis(
            "broken import",
            "A module or symbol referenced by the test does not exist.",
            "Check the page object exists under pages/ and the class name "
            "matches the import. If a dependency is genuinely missing it "
            "belongs in requirements.txt.",
        ),
    ),
    (
        re.compile(r"Element is not attached to the DOM|detached", re.I),
        Diagnosis(
            "element replaced mid-action",
            "The element was found, then removed from the DOM before the "
            "action completed - a single-page app re-rendered the component "
            "underneath the test.",
            "Re-resolve after the event that triggers the re-render rather "
            "than holding a locator across it. For inputs, type_and_confirm() "
            "reads the value back and retypes if the field was wiped.",
        ),
    ),
    (
        re.compile(r"net::ERR|ERR_CONNECTION|ERR_NAME_NOT_RESOLVED", re.I),
        Diagnosis(
            "application unreachable",
            "The browser could not reach the application at all. This is "
            "environment, not a test defect.",
            "Check `app_under_test.base_url` in config.yaml and that the "
            "target is up. If it is a public demo, it may simply be down.",
        ),
    ),
]

_UNKNOWN = Diagnosis(
    "unclassified",
    "This failure does not match a known signature, so the reading below is "
    "generic.",
    "Open reports/failure-evidence/ from the run artifact: a screenshot, a "
    "video and a Playwright trace were captured for this test. View the trace "
    "with `playwright show-trace <file>.trace.zip` - it replays every action "
    "and shows the DOM at the moment of failure.",
)


def diagnose(error_text: str) -> Diagnosis:
    """Best reading of a failure message. Never raises, always returns one."""
    text = error_text or ""
    for pattern, diagnosis in _SIGNATURES:
        if pattern.search(text):
            return diagnosis
    return _UNKNOWN


def format_failure(test_name: str, error_text: str,
                   indent: str = "  ") -> str:
    """A short, readable block for a log or a job summary."""
    first = (error_text or "").strip().splitlines()
    headline = first[0][:300] if first else "(no message)"
    d = diagnose(error_text)
    lines = [f"{indent}FAILED {test_name}", f"{indent}WHAT:  {headline}"]
    lines += d.as_lines(indent)
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════
# Classifying a failure whose evidence is NOT in the traceback
#
# `BasePage.is_showing()` swallows the Playwright error by design and logs it
# at WARNING, so a readiness assertion surfaces as nothing but `assert False`.
# The sentence that classifies the failure - "PRESENT in the DOM but HIDDEN" -
# lands in the CAPTURED LOG, and the captured log is not part of
# `report.longrepr`. Both callers passed only the traceback, so a failure this
# module can read perfectly was reported "unclassified" while its own diagnosis
# was printed six lines above.
#
# The widening is PROGRESSIVE and only ever runs on text that already came back
# unclassified. That is deliberate: matching over more text can only create new
# false positives, so every reading that is correct today stays byte-identical,
# and the extra sources are consulted in order of how much they can be trusted.
# ═════════════════════════════════════════════════════════════════════════

def diagnose_with_context(primary: str, *supplementary: str) -> Diagnosis:
    """Read PRIMARY; widen into SUPPLEMENTARY only while unclassified.

    PRIMARY is the traceback. SUPPLEMENTARY should be passed most-trustworthy
    first (captured log, then stdout, then stderr): each is appended in turn
    and the result returned as soon as anything matches.

    A caller that passes no supplementary text gets exactly `diagnose()`.
    """
    text = primary or ""
    result = diagnose(text)
    if result is not _UNKNOWN:
        return result

    for extra in supplementary:
        if not extra:
            continue
        text = f"{text}\n{extra}"
        result = diagnose(text)
        if result is not _UNKNOWN:
            return result
    return _UNKNOWN


def attach_diagnosis(report) -> bool:
    """Attach a CAUSE / FIX section to one failed pytest report.

    Lives here rather than inline in a conftest hook so that the behaviour is
    importable and can be exercised by a test. The previous version was four
    lines inside `pytest_runtest_makereport`, which meant the only thing a
    guard could check was that `diagnose()` classifies a string - never that
    the string the hook actually hands it is the one that carries the answer.
    It was not, for a year.

    Returns True if a section was attached. Never raises: a diagnosis is a
    convenience and must not be able to turn a test failure into an error, or
    mask a real result.
    """
    try:
        if not getattr(report, "failed", False):
            return False

        d = diagnose_with_context(
            str(report.longrepr),
            getattr(report, "caplog", "") or "",
            getattr(report, "capstdout", "") or "",
            getattr(report, "capstderr", "") or "",
        )
        report.sections.append((
            "Why this failed",
            f"CAUSE ({d.label}): {d.cause}\n\nFIX: {d.remedy}",
        ))
        return True
    except Exception:                                     # noqa: BLE001
        return False