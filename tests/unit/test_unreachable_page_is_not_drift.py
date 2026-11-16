"""A page the nightly check could not read for a moment is not a changed page.

Only a page that answered "not found" seeds Agent 0's impact analysis; a
timeout, a refusal or a server error is reported with its reason and left out,
and a report written before reasons were recorded keeps the old reading."""
from types import SimpleNamespace

from core import impact_analysis as ia
from core.inventory_update import build_update, render_body
from inventory_tools import browser
from inventory_tools.introspect import split_unreachable, summarize_drift


class _Page:
    """Just enough of a Playwright page for resolve_selectors."""

    def __init__(self, status=None, raises=None):
        self.status, self.raises = status, raises

    def goto(self, url, wait_until=None):
        if self.raises:
            raise self.raises
        return SimpleNamespace(status=self.status)

    def wait_for_load_state(self, *a, **k):
        return None

    def wait_for_timeout(self, *a, **k):
        return None


def _resolve(page, monkeypatch):
    monkeypatch.setattr(browser, "count_on_page", lambda *a, **k: ({}, set()))
    detail = {}
    _counts, _ids, reachable = browser.resolve_selectors(page, "https://x/p", [], detail=detail)
    return reachable, detail


def test_a_not_found_page_is_recorded_with_its_status(monkeypatch):
    reachable, detail = _resolve(_Page(status=404), monkeypatch)
    assert reachable is False and detail == {"status": 404, "reason": "HTTP 404"}


def test_a_failed_navigation_is_recorded_without_a_status(monkeypatch):
    reachable, detail = _resolve(_Page(raises=TimeoutError("Timeout 30000ms exceeded.\nmore")),
                                 monkeypatch)
    assert reachable is False and detail["status"] is None
    assert detail["reason"] == "navigation failed: TimeoutError (Timeout 30000ms exceeded.)"


def test_a_reachable_page_leaves_the_detail_empty(monkeypatch):
    reachable, detail = _resolve(_Page(status=200), monkeypatch)
    assert reachable is True and detail == {}


def test_callers_without_detail_keep_working(monkeypatch):
    monkeypatch.setattr(browser, "count_on_page", lambda *a, **k: ({}, set()))
    assert browser.resolve_selectors(_Page(status=503), "https://x/p", [])[2] is False


def _report(reasons):
    return summarize_drift({}, list(reasons), reasons)


def test_only_a_gone_page_seeds_impact_analysis():
    report = _report({"a": {"status": 404, "reason": "HTTP 404"},
                      "b": {"status": 410, "reason": "HTTP 410"},
                      "c": {"status": None, "reason": "navigation failed: TimeoutError"},
                      "d": {"status": 403, "reason": "HTTP 403"},
                      "e": {"status": 503, "reason": "HTTP 503"}})
    assert split_unreachable(report) == (["a", "b"], ["c", "d", "e"])
    assert ia.drift_seeds(report).pages == {"a", "b"}


def test_pages_not_read_for_a_moment_seed_nothing():
    report = _report({"p": {"status": None, "reason": "navigation failed: TimeoutError"},
                      "q": {"status": 429, "reason": "HTTP 429"}})
    seeds = ia.drift_seeds(report)
    assert seeds.pages == set() and seeds.empty()


def test_a_report_from_before_reasons_keeps_the_old_reading():
    old = {"pages": {}, "unreachable_pages": ["p", "q"]}
    assert split_unreachable(old) == (["p", "q"], [])
    assert ia.drift_seeds(old).pages == {"p", "q"}


def test_a_page_with_no_recorded_reason_in_a_new_report_is_not_gone():
    report = {"pages": {}, "unreachable_pages": ["p"], "unreachable_reasons": {}}
    assert split_unreachable(report) == ([], ["p"])


def test_unreachable_pages_still_count_as_drift_in_the_report():
    # The nightly check stays honest: a page it could not read is reported.
    report = _report({"p": {"status": None, "reason": "navigation failed: TimeoutError"}})
    assert report["has_drift"] is True and report["unreachable_pages"] == ["p"]
    assert report["unreachable_reasons"]["p"]["reason"].startswith("navigation failed")


def test_the_inventory_update_names_why_a_page_was_not_checked():
    drift = {"pages_checked": 0, "pages": {}, "unreachable_pages": ["p", "q"],
             "unreachable_reasons": {"p": {"status": 403, "reason": "HTTP 403"}}}
    upd = build_update(drift, {"pages": {}}, set())
    assert upd.unreachable_reasons["p"]["reason"] == "HTTP 403"
    text = render_body(upd, "inventory.json", "digest")
    assert "`p` (HTTP 403)" in text and "`q`" in text
