"""A hidden-element failure names the requests that failed while it waited.

Found on PRs #177-#179: product-detail "Add to cart" never showed its
confirmation in three scenarios, intermittently, on identical code. The message
blamed state stored against a signed-in user - the scenarios sign nobody in -
and nothing said whether the application had even answered the click. The
page now records failed requests and HTTP errors (blocked third parties
excluded) and the failure message carries them.

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


def _response(status, url, method="GET"):
    return MagicMock(status=status, url=url, request=MagicMock(method=method))


def _failed(url, why="net::ERR_TIMED_OUT"):
    return MagicMock(method="GET", url=url, failure=why)


def test_errors_and_failures_are_recorded_and_blocked_hosts_ignored():
    page = FakePage()
    bp.watch_network(page, ignore=lambda url: "ads.example" in url)
    page.emit("response", _response(200, "https://app.example/ok"))
    page.emit("response", _response(503, "https://app.example/add/1"))
    page.emit("requestfailed", _failed("https://app.example/add/2"))
    page.emit("requestfailed", _failed("https://ads.example/x", "net::ERR_FAILED"))
    assert bp.network_problems(page) == [
        "GET https://app.example/add/1 - HTTP 503",
        "GET https://app.example/add/2 - no response (net::ERR_TIMED_OUT)"]


def test_the_list_is_bounded():
    page = FakePage()
    bp.watch_network(page)
    for i in range(50):
        page.emit("response", _response(500, f"https://app.example/{i}"))
    assert len(bp.network_problems(page)) == bp._NETWORK_PROBLEMS_KEPT


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


def test_a_hidden_element_message_names_the_failed_request(monkeypatch):
    page = FakePage()
    bp.watch_network(page)
    page.emit("response", _response(503, "https://app.example/add/1"))
    msg = _hidden_failure(page, monkeypatch)
    assert "PRESENT in the DOM but HIDDEN" in msg
    assert "GET https://app.example/add/1 - HTTP 503" in msg
    assert diagnose(msg).label == "action's request failed"


def test_no_failed_request_says_so_and_keeps_the_state_diagnosis(monkeypatch):
    page = FakePage()
    bp.watch_network(page)
    msg = _hidden_failure(page, monkeypatch)
    assert "No request on this page failed" in msg
    assert diagnose(msg).label == "element present but hidden"


def test_an_unwatched_page_adds_nothing(monkeypatch):
    msg = _hidden_failure(FakePage(), monkeypatch)
    assert "request" not in msg.split("HIDDEN", 1)[1].split("Two common causes")[0]
    assert diagnose(msg).label == "element present but hidden"
