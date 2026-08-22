"""What the repair loop is TOLD after a rejection.

WHAT HAPPENED
    A story was abandoned as unrepairable. The gate had one complaint, and it
    was a good one: a page object used a selector key that belongs to a
    different inventory page. The message named the file, the class, the key,
    the page and every legal alternative.

    The model saw none of it. `_summarize_validator_feedback` compacted the
    error with `error.split(":", 2)[-1].strip()[:150]`, a heuristic written
    for one error shape. Two colons into a selector error the split lands
    after "Available keys", so what survived was the key list alone,
    truncated mid-word:

        - add_row_buttons, confirm_modal, listing_heading,
          continue_button, record_cards, record_names,
          filter_button, filter_input, searched_

    No file, no key, no statement of what was wrong. The repair loop then
    reported that the model "changed nothing" and gave up.

    The repair message is the voice with the LAST WORD - it is what the model
    reads after a rejection - so it is the one place a summary must not lose
    the answer. This class of failure is already in the history under a
    different guise: four sources telling the model how to touch an element,
    and the one it read last steering it away from the fix.

AND THE MESSAGE ITSELF WAS WRONG
    It said "do not invent the key". The key was not invented. It existed,
    correctly named, on the shared navigation page. The model had reached
    ACROSS page objects - a different mistake, with a different fix, that the
    message described nowhere. It then advised requesting the element "in the
    plan's `notes`", which repair cannot do: repair regenerates a file, not
    the plan. The one instruction offered after a rejection was impossible to
    carry out.
"""
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.agent2_coder import _summarize_validator_feedback, _trim_error
from validators.method_resolution_validator import validate_page_object_selectors

_PROJECT = Path(__file__).resolve().parents[2]

_SELECTOR_ERROR = (
    "Selector inventory error in 'pages/some_page.py': class SomePage calls "
    "self.sel('a_key'), but 'a_key' is not an element on inventory page "
    "'some_page'. Available keys: alpha, bravo, charlie, delta, echo, "
    "foxtrot, golf, hotel, india, juliet, kilo. Do not invent the key."
)


# ─────────────────────────────────────────────────────────────────────────
# A summary must keep the part that says what to do
# ─────────────────────────────────────────────────────────────────────────

def test_the_summary_keeps_what_was_wrong():
    out = _summarize_validator_feedback([_SELECTOR_ERROR])

    assert "a_key" in out, (
        "the offending key vanished - the model cannot fix a key it is never "
        "shown"
    )
    assert "some_page.py" in out, "the file vanished"
    assert "not an element" in out, "the complaint itself vanished"


def test_the_summary_keeps_the_legal_alternatives():
    out = _summarize_validator_feedback([_SELECTOR_ERROR])
    assert "alpha" in out and "kilo" in out, (
        "the list of keys that WOULD be legal is the actionable half of this "
        "error"
    )


def test_a_long_error_is_cut_from_the_end_not_the_start():
    """Break the thing the guard guards.

    The old heuristic kept the TAIL. Every validator error puts the file, the
    class and the complaint first and the supporting detail last, so keeping
    the tail discards exactly the part that identifies the problem.
    """
    long_error = "Complaint about 'pages/x.py': " + ("detail. " * 400)
    trimmed = _trim_error(long_error)

    assert trimmed.startswith("Complaint about 'pages/x.py'"), (
        "the head names the file and the problem and must survive"
    )
    assert len(trimmed) < len(long_error)


def test_a_short_error_is_passed_through_whole():
    short = "Import resolution error in 'pages/x.py': no module named 'y'."
    assert _trim_error(short) == short


def test_a_lone_coverage_error_is_sent_whole():
    """The phrase alone is not enough when there is only one of them.

    This test used to assert the opposite, on the rationale that "a
    step-coverage run can carry dozens of these and the phrase is all that
    matters". True of dozens. False of one - and one is what a story died on.

    A single coverage error became thirty-four characters:

        - When I am on the listing page

    The model had already written a decorator carrying that exact text, under
    the wrong KEYWORD. Shown only the phrase, it found the phrase in its own
    file and correctly changed nothing; the repair loop then abandoned the
    story for changing nothing. The fix was in the sentence it never saw:
    `has no matching @when() decorator`.
    """
    err = ("Step coverage error in 'tests/step_defs/test_x.py': feature step "
           "`When I do a thing` has no matching @when() decorator. pytest-bdd "
           "would fail with StepDefinitionNotFoundError at collection time.")
    out = _summarize_validator_feedback([err])

    assert "@when" in out, "the keyword is the fix and must survive"
    assert "no matching" in out, "say what is wrong, not just which step"
    assert "test_x.py" in out, "say which file"


def test_many_coverage_errors_are_still_compacted_to_the_pattern():
    """Break the thing the guard guards.

    Sending fifty verbose errors whole would bury the model as surely as
    truncation starved it. Above the threshold the phrase IS the message,
    because every line is another instance of one mistake.
    """
    errors = [
        f"Step coverage error in 'tests/step_defs/test_x.py': feature step "
        f"`Then thing number {n}` has no matching @then() decorator."
        for n in range(20)
    ]
    out = _summarize_validator_feedback(errors)

    assert "Then thing number 0" in out
    assert "more similar error(s)" in out, "say how many were elided"
    assert out.count("Step coverage error in") == 0, (
        "at this count the phrases alone are the point"
    )


def test_the_summary_is_bounded():
    """It must not swing the other way. A hundred verbose errors pasted whole
    would bury the model as surely as truncation starved it."""
    out = _summarize_validator_feedback([_SELECTOR_ERROR] * 3)
    assert len(out) < 4000


# ─────────────────────────────────────────────────────────────────────────
# A key that exists, on another page, is not an invented key
# ─────────────────────────────────────────────────────────────────────────

def _page_object(inventory_page: str, key: str) -> SimpleNamespace:
    return SimpleNamespace(
        file_path="pages/some_page.py",
        content=textwrap.dedent(f'''
            from pages.base_page import BasePage

            class SomePage(BasePage):
                INVENTORY_PAGE = "{inventory_page}"

                def go(self) -> None:
                    self.click(self.sel("{key}"))
        '''),
    )


def _two_page_inventory(tmp_path: Path) -> Path:
    """A project root with an inventory holding the same key on one page only."""
    import json

    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "Test App",
        "pages": {
            "shared": {"url": "/", "elements": {"a_shared_link": "#shared"}},
            "listing": {"url": "/listing", "elements": {"grid": "#grid"}},
        },
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n"
        "  name: Test App\n"
        "  inventory_file: app_inventory/app.json\n", encoding="utf-8")
    return tmp_path


def test_a_key_owned_by_another_page_says_which_page(tmp_path):
    root = _two_page_inventory(tmp_path)
    errors = validate_page_object_selectors(
        [_page_object("listing", "a_shared_link")], root)

    assert len(errors) == 1
    message = errors[0]
    assert "'shared'" in message, "name the page that DOES own the key"
    # "invent" is a substring of "inventory", so match the accusation itself.
    assert "do not invent" not in message.lower(), (
        "the key was not invented - saying so sends the model looking for a "
        "mistake it did not make"
    )
    assert "notes" not in message, (
        "repair regenerates a file, not the plan, so advice about the plan's "
        "notes cannot be acted on at the moment it is given"
    )


def test_a_key_that_exists_nowhere_still_says_so(tmp_path):
    """Break the thing the guard guards. The cross-page branch must not
    swallow the genuine invented-key case - that one IS invented, and the
    remedy for it is different."""
    root = _two_page_inventory(tmp_path)
    errors = validate_page_object_selectors(
        [_page_object("listing", "no_such_key_anywhere")], root)

    assert len(errors) == 1
    message = errors[0]
    assert "nor on any other page" in message
    assert "grid" in message, "list the keys that would be legal here"


def test_a_key_on_its_own_page_is_accepted(tmp_path):
    root = _two_page_inventory(tmp_path)
    assert validate_page_object_selectors(
        [_page_object("listing", "grid")], root) == []


@pytest.mark.parametrize("bad_key", ["a_shared_link", "no_such_key_anywhere"])
def test_every_rejection_lists_the_keys_that_would_work(tmp_path, bad_key):
    """Whichever branch fires, the model needs the legal set. Rejecting
    without it is the shape that produced a repair attempt changing nothing."""
    root = _two_page_inventory(tmp_path)
    errors = validate_page_object_selectors(
        [_page_object("listing", bad_key)], root)

    assert errors and "grid" in errors[0]


# =========================================================================
# Several kinds of problem are not one pattern repeated
#
# WHAT HAPPENED
#   The many-errors regime compacts each error to its Gherkin phrase and
#   appends a tail naming the single remedy that pattern needs. It was built
#   for one problem repeated across a whole feature, and for that it is
#   right.
#
#   A repair then arrived with 18 errors of TWO kinds: eleven feature steps
#   with no decorator, and seven step definitions defined and never used.
#   Opposite fixes - add these, delete those. All 18 were flattened, the
#   first eight sent, and the tail told the model that every error meant a
#   decorator was missing and it should write more. Not one of the seven
#   "delete this" errors reached it.
#
#   So the model added decorators, which produced more unused ones, and the
#   next attempt looked the same. Four attempts, then the story failed. The
#   feedback was not merely lossy - it pointed the wrong way.
# =========================================================================


def _coverage_error(i: int) -> str:
    return (
        f"Step coverage error in 'tests/step_defs/t.py': feature step "
        f"`Then step {i}` (from 'features/f.feature') has no matching "
        f"@then() decorator. pytest-bdd would fail with "
        f"StepDefinitionNotFoundError at test collection time."
    )


def _unused_error(i: int) -> str:
    return (
        f"Unused step-definition error in 'tests/step_defs/t.py': "
        f"@then('old phrasing {i}') is defined but no scenario in "
        f"'features/f.feature' uses it. Either use it in a scenario or "
        f"delete the function."
    )


_MIXED = ([_coverage_error(i) for i in range(11)]
          + [_unused_error(i) for i in range(7)])


def test_every_kind_of_error_reaches_the_model():
    """The regression. A whole class was silently dropped."""
    out = _summarize_validator_feedback(_MIXED)
    assert "has no matching @then() decorator" in out, "coverage class missing"
    assert "is defined but no scenario" in out, (
        "the entire 'unused step definition' class was dropped, so the model "
        "was never told to delete anything"
    )


def test_the_tail_does_not_prescribe_one_remedy():
    """The tail asserted every error meant a decorator was MISSING, which is
    the opposite of what half of them said."""
    out = _summarize_validator_feedback(_MIXED)
    assert "write a decorator for" not in out, (
        "telling the model to add a decorator for every line, when seven "
        "errors ask it to delete definitions, makes each attempt worse"
    )
    assert "DIFFERENT kinds" in out


def test_no_class_can_crowd_out_another():
    """Round-robin. A class listed first must not use up the budget."""
    lopsided = [_coverage_error(i) for i in range(30)] + [_unused_error(0)]
    out = _summarize_validator_feedback(lopsided)
    assert "is defined but no scenario" in out, (
        "one error of a second kind, behind thirty of the first, must still "
        "be shown - it is the one the model would otherwise never fix"
    )


def test_the_hidden_count_is_broken_down_by_kind():
    out = _summarize_validator_feedback(_MIXED)
    assert "more step coverage error" in out
    assert "more unused step-definition error" in out


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# The single-class compaction was built deliberately and is right for what
# it was built for. Making the mixed case work must not disturb it.
# ─────────────────────────────────────────────────────────────────────────

def test_one_kind_repeated_keeps_the_old_compaction():
    out = _summarize_validator_feedback([_coverage_error(i) for i in range(34)])
    shown = [l for l in out.splitlines() if l.startswith("  - ")]
    assert all(l.startswith("  - Then step") for l in shown), (
        "with a single kind the phrase alone IS the message - compacting it "
        "is what stops the model drowning in repetition"
    )
    assert "write a decorator for" in out, "the one-kind remedy is correct here"


def test_a_small_mixed_set_is_still_sent_whole():
    """Under the verbatim threshold nothing is compacted, whatever the mix."""
    out = _summarize_validator_feedback([_coverage_error(0), _unused_error(0)])
    assert "StepDefinitionNotFoundError" in out
    assert "delete the function" in out