"""A failed test names the temporary server errors it met, so Agent 4 re-runs it.

Found on PR #215 (26 Oct): two E2E failures in one run, during a burst of HTTP
503 from the application under test. One read "cart row not found", the other
"element never appeared". Neither message named an HTTP error, and Agent 4's
re-run of temporary errors (`--only-rerun "HTTP (5xx|429)"`) reads only the
exception message - so both were reported as test failures. navigate()
retries a page load, but not a request an action makes (an add-to-cart call,
a link followed by a click).

Fake page and events; no browser, no application names.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import pages.base_page as bp
import tests.conftest as conftest
from core.failure_diagnosis import diagnose

ROOT = Path(__file__).resolve().parents[2]


class FakePage:
    url = "https://app.example/item/1"

    def __init__(self):
        self.handlers = {}

    def on(self, event, fn):
        self.handlers.setdefault(event, []).append(fn)

    def emit(self, event, obj):
        for fn in self.handlers.get(event, []):
            fn(obj)


def _answer(page, url, status, rtype="xhr", method="GET"):
    request = MagicMock(method=method, url=url, resource_type=rtype, failure=None)
    page.emit("response", MagicMock(status=status, request=request))


def _watched(ignore=None):
    page = FakePage()
    bp.watch_network(page, ignore=ignore)
    return page


def _only_rerun_regex() -> str:
    """The pattern the workflow really passes, so the two cannot drift apart."""
    text = (ROOT / ".github/workflows/agent4_runner.yml").read_text(encoding="utf-8")
    return re.search(r'--only-rerun "([^"]+)"', text).group(1)


def _as_rerunfailures_reads_it(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


# ── which errors count ──────────────────────────────────────────────────

def test_an_action_request_refused_with_503_is_recorded():
    page = _watched()
    _answer(page, "https://app.example/add/1", 503)
    assert bp.unrecovered_server_errors(page) == ["GET https://app.example/add/1 - HTTP 503"]


def test_a_rate_limit_counts_and_a_4xx_does_not():
    page = _watched()
    _answer(page, "https://app.example/a", 429)
    _answer(page, "https://app.example/b", 404)
    _answer(page, "https://app.example/c", 403, method="POST")
    assert bp.unrecovered_server_errors(page) == ["GET https://app.example/a - HTTP 429"]


def test_a_request_that_later_succeeded_is_not_counted():
    """navigate() retries a page load: the 503 it recovered from is not a cause."""
    page = _watched()
    _answer(page, "https://app.example/list", 503, rtype="document")
    _answer(page, "https://app.example/list", 200, rtype="document")
    assert bp.unrecovered_server_errors(page) == []


def test_static_resources_and_blocked_hosts_are_ignored():
    page = _watched(ignore=lambda url: "ads.example" in url)
    _answer(page, "https://app.example/style.css", 503, rtype="stylesheet")
    _answer(page, "https://ads.example/frame", 503, rtype="document")
    assert bp.unrecovered_server_errors(page) == []


def test_an_early_refusal_is_not_pushed_out_by_later_requests():
    page = _watched()
    _answer(page, "https://app.example/add/1", 503)
    for i in range(bp._NETWORK_LOG_KEPT * 2):
        _answer(page, f"https://app.example/ok/{i}", 200)
    assert bp.unrecovered_server_errors(page) == ["GET https://app.example/add/1 - HTTP 503"]


def test_a_page_never_watched_has_none():
    assert bp.unrecovered_server_errors(FakePage()) == []


# ── the restated failure ────────────────────────────────────────────────

def test_without_server_errors_the_failure_is_left_alone():
    assert bp.with_server_errors(AssertionError("row not found"), []) is None


def test_the_restated_failure_keeps_the_original_and_matches_the_rerun_rule():
    restated = bp.with_server_errors(AssertionError("Locator expected not to have count '0'"),
                                     ["GET https://app.example/add/1 - HTTP 503"])
    text = _as_rerunfailures_reads_it(restated)
    assert isinstance(restated, AssertionError)
    assert "Locator expected not to have count '0'" in text
    assert re.search(_only_rerun_regex(), text)


def test_a_plain_assertion_does_not_match_the_rerun_rule():
    assert not re.search(_only_rerun_regex(),
                         _as_rerunfailures_reads_it(AssertionError("expected 2, got 1")))


def test_the_reading_says_the_application_was_unavailable():
    restated = bp.with_server_errors(AssertionError("x"), ["GET https://app.example/p - HTTP 502"])
    assert diagnose(str(restated)).label == "application temporarily unavailable"


# ── the hook that applies it ────────────────────────────────────────────

def _item(page=None):
    item = MagicMock(spec=[])
    if page is not None:
        item._watched_page = page
    return item


def test_the_hook_restates_a_failure_that_met_a_server_error():
    page = _watched()
    _answer(page, "https://app.example/add/1", 503)
    hook = conftest.pytest_runtest_call(_item(page))
    next(hook)
    original = AssertionError("cart row not found")
    with pytest.raises(bp.ApplicationUnavailableError) as raised:
        hook.throw(original)
    assert raised.value.__cause__ is original
    assert re.search(_only_rerun_regex(), _as_rerunfailures_reads_it(raised.value))


def test_the_hook_leaves_other_failures_unchanged():
    for item in (_item(_watched()), _item()):
        hook = conftest.pytest_runtest_call(item)
        next(hook)
        original = AssertionError("expected 2, got 1")
        with pytest.raises(AssertionError) as raised:
            hook.throw(original)
        assert raised.value is original


def test_the_hook_passes_a_passing_test_through():
    hook = conftest.pytest_runtest_call(_item(_watched()))
    next(hook)
    with pytest.raises(StopIteration) as done:
        hook.send("result")
    assert done.value.value == "result"


def test_the_page_fixture_hands_its_page_to_the_hook():
    source = (ROOT / "tests/conftest.py").read_text(encoding="utf-8")
    assert "request.node._watched_page = page" in source
