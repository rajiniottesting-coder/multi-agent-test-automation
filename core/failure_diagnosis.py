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
        re.compile(r"Records Found|Record Found", re.I),
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
