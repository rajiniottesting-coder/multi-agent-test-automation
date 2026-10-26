"""A navigation that did not land must fail NOW, not 30 seconds later.

WHAT HAPPENED
    A CI run failed nine tests out of nine, each with an identical
    `Locator.fill: Timeout 30000ms exceeded` on the login email field, taking
    four and a half minutes in total. The reported cause - "covered by an
    overlay, disabled, or still animating" - was wrong for all nine. The page
    had never loaded.

    page.goto() treats any response as success. A 403, a 503, a bot-check
    interstitial and a captcha page are all "successful" navigations. The test
    then walks on and dies on the first locator, and the error names the
    element rather than the navigation, which is the wrong place to look.
"""
from types import SimpleNamespace

import json
import textwrap
import pytest

from pages.base_page import BasePage


class _Response:
    def __init__(self, status, ok=None, status_text=""):
        self.status = status
        self.ok = (200 <= status < 300) if ok is None else ok
        self.status_text = status_text


class _Page:
    """Minimal Playwright page stand-in. No browser."""

    def __init__(self, response):
        self._response = response
        self.went_to = None
        self.waits = []

    def goto(self, url):
        self.went_to = url
        return self._response

    def wait_for_timeout(self, ms):
        self.waits.append(ms)


def _page_object(response):
    obj = BasePage.__new__(BasePage)
    obj.page = _Page(response)
    return obj


def test_a_good_response_navigates_silently():
    obj = _page_object(_Response(200))
    obj.navigate("https://app.test/login")
    assert obj.page.went_to == "https://app.test/login"


@pytest.mark.parametrize("status,label,retried", [
    (403, "blocked - the usual shape of a datacentre IP being refused", False),
    (404, "wrong path", False),
    # A temporary error is retried first (test_outage_retry.py, L14), then
    # fails with the same message, plus how many attempts were made.
    (429, "rate limited", True),
    (500, "server error", True),
    (503, "unavailable", True),
])
def test_a_bad_response_fails_without_reaching_a_locator(status, label, retried, monkeypatch):
    monkeypatch.setattr(BasePage, "_NAV_RETRY_CACHE", (1, 1))
    obj = _page_object(_Response(status))
    with pytest.raises(AssertionError) as excinfo:
        obj.navigate("https://app.test/login")
    message = str(excinfo.value)
    assert str(status) in message, "the status code must be in the message"
    assert "did not load" in message
    assert "https://app.test/login" in message, "name the URL that failed"
    assert obj.page.waits == ([1, 1] if retried else []), label
    assert ("after 3 attempts" in message) is retried


def test_the_message_points_at_the_likely_CI_cause():
    """The failure this guards against happened in CI and not locally, so the
    message has to say where to look rather than leave it as a mystery."""
    obj = _page_object(_Response(403))
    with pytest.raises(AssertionError) as excinfo:
        obj.navigate("https://app.test/login")
    assert "blocking" in str(excinfo.value).lower()


def test_a_null_response_is_not_treated_as_a_failure():
    """goto() returns None for a same-document navigation - a fragment change,
    or a history push. That is not an error."""
    obj = _page_object(None)
    obj.navigate("https://app.test/page#section")


def test_a_redirect_that_ends_OK_is_accepted():
    """Playwright reports the FINAL response after following redirects, so a
    302 that lands on a 200 arrives here as a 200."""
    obj = _page_object(_Response(200))
    obj.navigate("https://app.test/login")


# ─────────────────────────────────────────────────────────────────────────
# click_nth works for ANY key, not only a declared family
#
# It is index-addressing, not family-addressing: index 0 of a key matching one
# element is that element. What it must never do is fail QUIETLY, or fail
# slowly with an error that sends the reader to the wrong place.
# ─────────────────────────────────────────────────────────────────────────

class _Locator:
    def __init__(self, count, on_click=None):
        self._count = count
        self._on_click = on_click
        self.clicked_index = None

    def nth(self, index):
        self._index = index
        return self

    def click(self, timeout=None):
        if self._index >= self._count:
            raise TimeoutError("locator resolved to no elements")
        self.clicked_index = self._index
        if self._on_click:
            self._on_click(self._index)

    def count(self):
        return self._count


def _with_locator(loc):
    obj = BasePage.__new__(BasePage)
    obj._locator = lambda selector: loc
    return obj


def test_index_zero_of_a_single_element_key_works():
    """A non-family key is not a special case - index 0 is that element."""
    loc = _Locator(count=1)
    _with_locator(loc).click_nth("#only", 0)
    assert loc.clicked_index == 0


def test_a_valid_index_of_a_family_works():
    loc = _Locator(count=3)
    _with_locator(loc).click_nth(".row", 2)
    assert loc.clicked_index == 2


@pytest.mark.parametrize("count,index", [(1, 10), (3, 99), (0, 0)])
def test_an_out_of_range_index_says_what_was_actually_there(count, index):
    """Left alone this waits out the full timeout and then reports a plain
    'element not found', which sends the reader to the selector rather than to
    the index. The count is taken AFTER the failure and named."""
    with pytest.raises(AssertionError) as excinfo:
        _with_locator(_Locator(count=count)).click_nth(".row", index)
    message = str(excinfo.value)
    assert f"index {index}" in message
    assert f"{count} element(s)" in message
    assert "find_row_index_by_text" in message, \
        "an index alone is brittle - point at the by-text route"


def test_a_genuine_failure_on_a_valid_index_is_not_reworded():
    """If the index IS in range, the original error must survive: an element
    that exists but is covered by an overlay is a different problem, and
    relabelling it as an index mistake would hide it."""
    class Covered(_Locator):
        def click(self, timeout=None):
            raise TimeoutError("element intercepts pointer events")
    with pytest.raises(TimeoutError):
        _with_locator(Covered(count=5)).click_nth(".row", 1)


# =========================================================================
# confirm_arrival() must not undo a navigation that WORKED
#
# WHAT HAPPENED
#   A generated shared-navigation page object ended `go_to_<somewhere>()`
#   with confirm_arrival(). That call re-issues the navigation to the url
#   THIS page object declares - the navigation entry's own url, the home
#   page. So a click that had correctly reached the listing was judged a
#   failure and the browser was sent home:
#
#       <Menu>Page.confirm_arrival(): expected /, found /<destination>.
#       The navigation that should have landed here did not - re-issuing.
#
#   The next step then waited its full timeout for a control that only
#   exists on the listing, and reported a selector timeout. Three scenarios
#   failed that way in one run, each blaming its own selector, on a suite
#   that had been green.
#
# TWO HALVES
#   Run time: refuse to re-issue when the browser is on ANOTHER page the
#   inventory declares - that is proof the navigation landed, just not here.
#   The interstitial case is untouched: there the click is consumed and the
#   browser sits on the previous page or a fragment, not on a different
#   declared destination.
#
#   Generation time: validate_confirm_arrival_targets_this_page rejects the
#   call in a method whose name points at a page that is not this object's.
# =========================================================================

from validators.method_resolution_validator import (
    validate_confirm_arrival_targets_this_page,
)


def _library_project(tmp_path):
    """A SECOND application, so this is a framework rule and not a fix for
    the configured app's page names."""
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "a.json").write_text(json.dumps({
        "app_name": "Bookworm Library",
        "pages": {
            "menu": {"url": "/", "page_object_class": "MenuPage",
                    "elements": {"loans_link": "#l"}},
            "loans": {"url": "/loans", "page_object_class": "LoansPage",
                      "elements": {"rows": ".row"}},
        }}), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Bookworm Library\n"
        "  inventory_file: app_inventory/a.json\n", encoding="utf-8")
    return tmp_path


def _arrival_page(cls: str, inventory_page: str, body: str):
    return SimpleNamespace(
        file_path=f"pages/{inventory_page}_page.py",
        content=("from pages.base_page import BasePage\n\n\n"
                 f"class {cls}(BasePage):\n"
                 f'    INVENTORY_PAGE = "{inventory_page}"\n')
                + textwrap.indent(textwrap.dedent(body), "    "),
    )


def test_confirming_arrival_after_leaving_this_page_is_rejected(tmp_path):
    """The regression."""
    errors = validate_confirm_arrival_targets_this_page(
        [_arrival_page("MenuPage", "menu", '''
            def go_to_loans(self):
                self.click(self.sel("loans_link"))
                self.confirm_arrival()
        ''')], _library_project(tmp_path))
    assert errors, (
        "confirm_arrival() on the object whose control was clicked sends the "
        "browser back off the page the click had just reached"
    )
    assert "loans" in errors[0] and "menu" in errors[0]


def test_the_message_says_where_the_call_belongs(tmp_path):
    errors = validate_confirm_arrival_targets_this_page(
        [_arrival_page("MenuPage", "menu", '''
            def go_to_loans(self):
                self.click(self.sel("loans_link"))
                self.confirm_arrival()
        ''')], _library_project(tmp_path))
    assert "where you ARRIVE" in errors[0]


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# confirm_arrival() is load-bearing against ad interstitials. A check that
# discouraged it generally would reopen the failure it was built for.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cls,inv,body", [
    # confirming arrival on THIS page object's own page - the correct use
    ("LoansPage", "loans", '''
        def open_loans(self, base_url):
            self.navigate(base_url)
            self.confirm_arrival()
    '''),
    # leaving, but not claiming to have arrived
    ("MenuPage", "menu", '''
        def go_to_loans(self):
            self.click(self.sel("loans_link"))
    '''),
    # a method that does not navigate at all
    ("LoansPage", "loans", '''
        def refresh_rows(self):
            self.reload()
            self.confirm_arrival()
    '''),
])
def test_correct_uses_are_not_flagged(tmp_path, cls, inv, body):
    assert validate_confirm_arrival_targets_this_page(
        [_arrival_page(cls, inv, body)], _library_project(tmp_path)) == []


def test_a_destination_the_inventory_does_not_know_is_not_flagged(tmp_path):
    """`open_dialog()` names no page, so the word is part of a verb phrase
    rather than a destination."""
    assert validate_confirm_arrival_targets_this_page(
        [_arrival_page("LoansPage", "loans", '''
            def open_dialog(self):
                self.click(self.sel("rows"))
                self.confirm_arrival()
        ''')], _library_project(tmp_path)) == []