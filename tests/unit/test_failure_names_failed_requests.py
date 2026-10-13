"""A hidden-element failure says what the page's action requests did.

Found on PRs #177-#180: product-detail "Add to cart" never showed its
confirmation in some scenarios, intermittently, on identical code. The first
message blamed state stored against a signed-in user (those scenarios sign
nobody in); the next version listed EVERY failed request, so fonts blocked as
mixed content on every page read as the cause. Only action requests - XHR,
fetch, navigations - are evidence about an action; static resources are not.

Fake page and events; no browser, no application names.
"""
from unittest.mock import MagicMock

import pytest

import pages.base_page as bp
from core.failure_diagnosis import diagnose


class FakePage:
    url = "https://app.example/item/1"

    def __init__(self):
        self.handlers = {}

    def on(self, event, fn):
        self.handlers.setdefault(event, []).append(fn)

    def emit(self, event, obj):
        for fn in self.handlers.get(event, []):
            fn(obj)


def _req(url, rtype="xhr", status=None, failure=None, method="GET"):
    r = MagicMock(method=method, url=url, resource_type=rtype, failure=failure)
    r.response.return_value = None if status is None else MagicMock(status=status)
    return r


def _finish(page, url, status, rtype="xhr"):
    page.emit("response", MagicMock(status=status, request=_req(url, rtype)))


def _fail(page, url, why="net::ERR_TIMED_OUT", rtype="xhr"):
    page.emit("requestfailed", _req(url, rtype, failure=why))


def test_only_action_requests_count_and_blocked_hosts_are_ignored():
    page = FakePage()
    bp.watch_network(page, ignore=lambda url: "ads.example" in url)
    _fail(page, "http://fonts.example/css", "mixed-content", rtype="stylesheet")
    _fail(page, "https://ads.example/x", "net::ERR_FAILED", rtype="script")
    _fail(page, "https://ads.example/frame", "net::ERR_FAILED", rtype="document")
    _finish(page, "https://app.example/add/1", 503)
    _fail(page, "https://app.example/add/2")
    assert bp.network_problems(page) == [
        "GET https://app.example/add/1 - HTTP 503",
        "GET https://app.example/add/2 - no response (net::ERR_TIMED_OUT)"]


def test_the_log_is_bounded():
    page = FakePage()
    bp.watch_network(page)
    for i in range(50):
        _finish(page, f"https://app.example/{i}", 500)
    assert len(bp.network_problems(page)) == bp._NETWORK_LOG_KEPT


def _hidden_failure(page, monkeypatch):
    target = MagicMock()
    target.count.return_value = 1
    obj = bp.BasePage.__new__(bp.BasePage)
    obj.page = page
    monkeypatch.setattr(obj, "_locator", lambda loc: target, raising=False)
    monkeypatch.setattr(bp, "expect", lambda t: MagicMock(
        to_be_visible=MagicMock(side_effect=AssertionError("not visible"))))
    with pytest.raises(AssertionError) as e:
        obj.wait_visible("#confirm", timeout_ms=1)
    return str(e.value)


def test_a_failed_action_request_is_named_and_diagnosed(monkeypatch):
    page = FakePage()
    bp.watch_network(page)
    _finish(page, "https://app.example/item/1", 200, rtype="document")
    _finish(page, "https://app.example/add/1", 503)
    msg = _hidden_failure(page, monkeypatch)
    assert "GET https://app.example/add/1 - HTTP 503" in msg
    assert diagnose(msg).label == "action's request failed"


def test_a_failing_font_is_not_evidence(monkeypatch):
    """The PR #180 misreading: mixed-content fonts fail on every page."""
    page = FakePage()
    bp.watch_network(page)
    _finish(page, "https://app.example/item/1", 200, rtype="document")
    _fail(page, "http://fonts.example/css", "mixed-content", rtype="stylesheet")
    msg = _hidden_failure(page, monkeypatch)
    assert "fonts.example" not in msg
    assert "Every action request on this page succeeded" in msg
    assert "never reached the application" in msg
    assert diagnose(msg).label == "element present but hidden"


def test_successful_action_requests_are_listed(monkeypatch):
    page = FakePage()
    bp.watch_network(page)
    _finish(page, "https://app.example/add/1", 200)
    msg = _hidden_failure(page, monkeypatch)
    assert "GET https://app.example/add/1 - HTTP 200" in msg


def test_no_action_request_at_all_says_so(monkeypatch):
    page = FakePage()
    bp.watch_network(page)
    msg = _hidden_failure(page, monkeypatch)
    assert "made no XHR, fetch or navigation request" in msg


def test_an_unwatched_page_adds_nothing(monkeypatch):
    msg = _hidden_failure(FakePage(), monkeypatch)
    assert "request" not in msg.split("Two common causes")[0]
    assert diagnose(msg).label == "element present but hidden"
