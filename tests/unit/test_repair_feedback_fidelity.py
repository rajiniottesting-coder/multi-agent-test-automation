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


def test_step_coverage_errors_still_extract_just_the_phrase():
    """The one shape the old heuristic was written for must keep working -
    a step-coverage run can carry dozens of these and the phrase is all that
    matters."""
    err = "Step coverage error: no definition for feature step `I do a thing`"
    out = _summarize_validator_feedback([err])

    assert out.strip() == "- I do a thing"


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