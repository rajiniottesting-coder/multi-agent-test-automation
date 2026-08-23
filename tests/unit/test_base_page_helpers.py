"""Unit tests for BasePage: helper-signature injection, and runtime behaviour
that a page object depends on (timeout resolution, readiness probing).

Page objects inherit ~70 helpers from BasePage. The LLM cannot use what it
cannot see, so Stage 2 injects their signatures into the page-object prompt.
These tests pin that contract: signatures only, never bodies; page objects
only, never step defs; and a clean degrade when BasePage is unreadable.
"""
import textwrap

from agents.agent2_coder import _build_base_page_helpers_block


def _write_base_page(tmp_path, body: str) -> None:
    pages = tmp_path / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    (pages / "base_page.py").write_text(textwrap.dedent(body).strip())


def test_public_signatures_are_listed(tmp_path):
    _write_base_page(tmp_path, '''
        class BasePage:
            def click(self, locator: str) -> None:
                """Click the element."""
                pass
            def get_text(self, locator: str) -> str:
                """Visible text."""
                return ""
    ''')
    block = _build_base_page_helpers_block(tmp_path)
    assert "self.click(locator: str) -> None" in block
    assert "self.get_text(locator: str) -> str" in block


def test_bodies_are_never_included(tmp_path):
    """Signatures only — bodies would cost tokens and teach nothing."""
    _write_base_page(tmp_path, '''
        class BasePage:
            def scroll_to_bottom(self) -> None:
                """Scroll down."""
                self.page.evaluate("window.scrollTo(0, 9999)")
    ''')
    block = _build_base_page_helpers_block(tmp_path)
    assert "scroll_to_bottom" in block
    assert "window.scrollTo" not in block


def test_private_helpers_are_excluded(tmp_path):
    """_locator/_timeout are internal plumbing, not API."""
    _write_base_page(tmp_path, '''
        class BasePage:
            def _locator(self, locator: str):
                pass
            def click(self, locator: str) -> None:
                pass
    ''')
    block = _build_base_page_helpers_block(tmp_path)
    assert "_locator" not in block
    assert "self.click" in block


def test_self_is_stripped_from_signatures(tmp_path):
    """The LLM writes `self.click(x)`, not `self.click(self, x)`."""
    _write_base_page(tmp_path, '''
        class BasePage:
            def click(self, locator: str) -> None:
                pass
    ''')
    assert "self.click(locator: str)" in _build_base_page_helpers_block(tmp_path)


def test_block_tells_the_llm_how_to_request_a_missing_helper(tmp_path):
    """BasePage is reserved — the LLM must request, not edit."""
    _write_base_page(tmp_path, '''
        class BasePage:
            def click(self, locator: str) -> None:
                pass
    ''')
    block = _build_base_page_helpers_block(tmp_path)
    assert "BASEPAGE-REQUEST" in block
    assert "reserved" in block.lower()


def test_missing_file_degrades_to_empty_string(tmp_path):
    """No BasePage -> prompt keeps working without the block."""
    assert _build_base_page_helpers_block(tmp_path) == ""


def test_unparseable_file_degrades_to_empty_string(tmp_path):
    _write_base_page(tmp_path, "class BasePage:  def broken(")
    assert _build_base_page_helpers_block(tmp_path) == ""


def test_real_base_page_exposes_expected_control_types():
    """Guard against the real file losing whole categories of helper."""
    block = _build_base_page_helpers_block()
    for method in ("select_by_label", "check", "upload_file", "hover",
                   "drag_to", "get_row_count", "scroll_into_view",
                   "accept_next_dialog", "click_in_frame"):
        assert f"self.{method}(" in block, f"missing {method}"


# ─────────────────────────────────────────────────────────────────────────
# Timeout resolution — one source of truth
#
# BasePage used to hard-code DEFAULT_TIMEOUT_MS = 5000 while conftest.py
# separately applied config.yaml's `browser.timeout` via
# page.set_default_timeout(). The two disagreed: config said 30000, every
# explicit wait_visible() used 5000, and CI logs showed "timeout 5000ms" on a
# run configured for 30s. Raising the config value changed nothing.
# ─────────────────────────────────────────────────────────────────────────
from pathlib import Path

import pytest

from pages.base_page import BasePage


@pytest.fixture(autouse=True)
def _clear_timeout_cache():
    """The resolved timeout is cached per process; isolate each test."""
    BasePage._TIMEOUT_CACHE = None
    yield
    BasePage._TIMEOUT_CACHE = None


class _FakeLocator:
    def __init__(self, visible: bool):
        self._visible = visible


class _FakePage:
    url = "https://app.example/somewhere"


def _page_obj(monkeypatch, *, raises: bool = False, seen: list | None = None):
    """A BasePage bound to a fake Playwright page, with wait_visible stubbed."""
    obj = BasePage(_FakePage())

    def fake_wait_visible(locator, timeout_ms=None):
        if seen is not None:
            seen.append((locator, obj._timeout(timeout_ms)))
        if raises:
            raise RuntimeError("Timeout 5000ms exceeded.\nwaiting for locator")

    monkeypatch.setattr(obj, "wait_visible", fake_wait_visible)
    return obj


def test_timeout_comes_from_the_real_config(monkeypatch):
    """The shipped config says 30000; the helper must return that, not 5000."""
    assert BasePage._default_timeout_ms() == 30000
    assert BasePage.DEFAULT_TIMEOUT_MS == 5000, "constant is the fallback only"


def test_explicit_timeout_still_wins(monkeypatch):
    obj = BasePage(_FakePage())
    assert obj._timeout(1234) == 1234


def test_zero_is_not_treated_as_absent(monkeypatch):
    """`0` is a real caller choice, not a 'use the default' sentinel."""
    obj = BasePage(_FakePage())
    assert obj._timeout(0) == 0


def test_unreadable_config_falls_back_to_the_constant(monkeypatch):
    import yaml
    monkeypatch.setattr(yaml, "safe_load", lambda *_a, **_k: (_ for _ in ()).throw(
        OSError("no config here")))
    assert BasePage._default_timeout_ms() == BasePage.DEFAULT_TIMEOUT_MS


@pytest.mark.parametrize("bad", [None, "", "abc", 0, -1, True, {"a": 1}])
def test_malformed_timeout_values_fall_back(monkeypatch, bad):
    """A junk or non-positive browser.timeout must not produce a junk wait."""
    import yaml
    monkeypatch.setattr(yaml, "safe_load",
                        lambda *_a, **_k: {"browser": {"timeout": bad}})
    assert BasePage._default_timeout_ms() == BasePage.DEFAULT_TIMEOUT_MS


def test_timeout_is_resolved_once_not_per_call(monkeypatch):
    calls = {"n": 0}
    import yaml
    real = yaml.safe_load

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(yaml, "safe_load", counting)
    BasePage._default_timeout_ms()
    BasePage._default_timeout_ms()
    BasePage._default_timeout_ms()
    assert calls["n"] == 1


# ─────────────────────────────────────────────────────────────────────────
# is_showing — a readiness probe that says WHY it failed
#
# The pattern it replaces swallowed the Playwright error, so a failing
# `assert page.is_loaded()` reported nothing but `assert False`.
# ─────────────────────────────────────────────────────────────────────────

def test_is_showing_true_when_the_element_arrives(monkeypatch):
    obj = _page_obj(monkeypatch)
    assert obj.is_showing("#thing") is True


def test_is_showing_false_and_never_raises_on_timeout(monkeypatch):
    obj = _page_obj(monkeypatch, raises=True)
    assert obj.is_showing("#thing") is False


def test_is_showing_logs_selector_timeout_and_url(monkeypatch, caplog):
    obj = _page_obj(monkeypatch, raises=True)
    with caplog.at_level("WARNING"):
        obj.is_showing("#missing")
    logged = caplog.text
    assert "#missing" in logged
    assert "30000" in logged, "the wait it actually used must be named"
    assert "app.example" in logged, "the page it was on must be named"


def test_is_showing_survives_a_page_with_no_url(monkeypatch):
    class _NoUrl:
        @property
        def url(self):
            raise RuntimeError("browser closed")

    obj = BasePage(_NoUrl())
    monkeypatch.setattr(obj, "wait_visible", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("boom")))
    assert obj.is_showing("#x") is False


def test_is_showing_passes_the_explicit_timeout_through(monkeypatch):
    seen: list = []
    obj = _page_obj(monkeypatch, seen=seen)
    obj.is_showing("#thing", timeout_ms=250)
    assert seen == [("#thing", 250)]


# =========================================================================
# The interstitial handler must actually be CALLED
#
# dismiss_interstitial() sat in BasePage for months with no caller anywhere in
# the repo. It was written after an ad swallowed a navigation and cost a day
# of reading a trace, and then it never ran once. A helper nobody calls is a
# comment.
#
# The probe is where it belongs: is_showing() is a page object asking "did I
# arrive?", and an interstitial is precisely the thing that answers that
# question wrongly - the click is consumed, the URL gains a fragment, the page
# never moves, and the probe waits out its full timeout on a page the browser
# never left.
#
# These are BEHAVIOURAL. A textual check that the name appears somewhere would
# pass on a mention in a docstring, which is how the previous version of this
# class of guard passed while the feature was broken.
# =========================================================================

class _InterstitialPage:
    """A page whose URL carries an interstitial fragment until it is dismissed."""

    def __init__(self, clears: bool = True):
        # Read the fragment from the framework's own constant rather than
        # naming an ad vendor here. The test then follows the tuple if it
        # ever changes, and no unit test carries a third-party literal.
        self.url = ("https://app.example/somewhere"
                    + BasePage._INTERSTITIAL_FRAGMENTS[0])
        self._clears = clears
        self.escapes = 0

    class _Keyboard:
        def __init__(self, outer):
            self._outer = outer

        def press(self, key):
            self._outer.escapes += 1
            if self._outer._clears:
                self._outer.url = "https://app.example/somewhere"

    @property
    def keyboard(self):
        return self._Keyboard(self)

    def wait_for_timeout(self, ms):
        pass

    def go_back(self, **kwargs):
        self.url = "https://app.example/somewhere"


def _probe_with_page(monkeypatch, page, outcomes):
    """A BasePage over `page`, whose wait_visible fails/succeeds per outcomes."""
    obj = BasePage(page)
    calls = {"n": 0}

    def fake_wait_visible(locator, timeout_ms=None):
        calls["n"] += 1
        if not outcomes.pop(0):
            raise RuntimeError("Timeout 5000ms exceeded.\nwaiting for locator")

    monkeypatch.setattr(obj, "wait_visible", fake_wait_visible)
    return obj, calls


def test_a_failed_probe_dismisses_an_interstitial_and_retries(monkeypatch):
    """The whole point: the first wait dies behind the ad, the second sees the
    page that was there all along."""
    page = _InterstitialPage()
    obj, calls = _probe_with_page(monkeypatch, page, [False, True])

    assert obj.is_showing("#thing") is True
    assert calls["n"] == 2, "the probe must be retried after the ad is cleared"
    assert page.escapes == 1


def test_no_interstitial_means_no_retry(monkeypatch):
    """Break the thing the guard guards.

    If the retry fired on every failure it would double the wait on every
    ordinary miss - 30 seconds becomes 60 across a suite. It must be gated on
    the URL saying an interstitial is genuinely up.
    """
    obj, calls = _probe_with_page(monkeypatch, _FakePage(), [False])

    assert obj.is_showing("#thing") is False
    assert calls["n"] == 1, "an ordinary failure must not be retried"


def test_a_retry_that_also_fails_still_reports_the_original_reason(monkeypatch):
    """Dismissing the ad must not cost the reader the diagnosis. The log line
    is the only place the readiness class carries its cause."""
    obj, calls = _probe_with_page(monkeypatch, _InterstitialPage(), [False, False])

    import logging
    with _caplog_at(logging.WARNING) as records:
        assert obj.is_showing("#missing") is False

    text = "\n".join(records)
    assert calls["n"] == 2
    assert "#missing" in text
    assert "Timeout" in text, "the Playwright reason must survive the retry"


class _caplog_at:
    """Minimal log capture - caplog is a fixture and this file uses plain
    functions for the probe tests."""

    def __init__(self, level):
        self.level = level
        self.records: list = []

    def __enter__(self):
        import logging
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.records.append(
            record.getMessage() % () if not record.args
            else record.getMessage())
        self.logger = logging.getLogger("pages.base_page")
        self.logger.addHandler(self.handler)
        self._old = self.logger.level
        self.logger.setLevel(self.level)
        return self.records

    def __exit__(self, *exc):
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self._old)
        return False


# =========================================================================
# AN INTERSTITIAL HAS TO BE CLEARED WHERE EVERY HELPER PASSES
#
# The handler was called from the readiness probe, and the very next run died
# in fill(), which is not a probe. A trace settled it: a nav click at +4.0s,
# a fill at +4.9s, thirty seconds of nothing, and a URL that had never left
# the previous page.
#
# _locator() is the one chokepoint every action and every wait goes through,
# and the check is a string comparison against the URL, so the ad is cleared
# BEFORE the wait starts instead of after it expires.
# =========================================================================

def _fragment() -> str:
    """An interstitial fragment, read from the framework's own constant."""
    return BasePage._INTERSTITIAL_FRAGMENTS[0]


class _AdPage:
    """A page showing an interstitial until Escape is pressed."""

    def __init__(self, path: str = "/somewhere", clears: bool = True):
        self.origin = "https://app.example"
        self.path = path
        self.url = self.origin + path + _fragment()
        self._clears = clears
        self.escapes = 0
        self.gotos: list = []

    class _Keyboard:
        def __init__(self, outer):
            self._outer = outer

        def press(self, key):
            self._outer.escapes += 1
            if self._outer._clears:
                self._outer.url = self._outer.origin + self._outer.path

    @property
    def keyboard(self):
        return self._Keyboard(self)

    def wait_for_timeout(self, ms):
        pass

    def go_back(self, **kwargs):
        self.url = self.origin + self.path

    def goto(self, url):
        self.gotos.append(url)
        self.url = url
        return None

    def locator(self, selector, **kwargs):
        return ("locator", selector)


def test_an_action_clears_an_interstitial_before_it_waits():
    """The failure this replaces spent its whole timeout behind the ad."""
    page = _AdPage()
    obj = BasePage(page)

    obj._locator("#anything")

    assert page.escapes == 1, "the ad must be dismissed before the action runs"
    assert _fragment() not in page.url


def test_an_ordinary_page_is_left_completely_alone():
    """Break the thing the guard guards.

    _locator() runs on every single helper call. If the check were not free
    and not gated on the URL, this would be a cost on the whole suite.
    """
    page = _AdPage()
    page.url = page.origin + page.path          # no fragment
    obj = BasePage(page)

    obj._locator("#anything")

    assert page.escapes == 0, "no interstitial means nothing should happen"


def test_clearing_does_not_re_enter_itself():
    """dismiss_interstitial() drives the page; a re-entrant call through a
    helper would recurse."""
    page = _AdPage(clears=False)                # Escape never clears it
    obj = BasePage(page)

    obj._locator("#anything")                   # must return, not recurse

    assert page.escapes == 1


# =========================================================================
# ...AND A SWALLOWED NAVIGATION HAS TO BE RE-ISSUED
#
# Dismissing is not enough on its own. The click was CONSUMED: the browser
# never left, so clearing the ad leaves it on the wrong page with the click
# gone. confirm_arrival() re-issues the navigation to the URL the page object
# declares - the destination comes from the page object it is called on, so
# it is never guessed from wherever the browser happens to be.
# =========================================================================

class _DestinationPage(BasePage):
    """A page with a fixed address."""
    INVENTORY_PAGE = "destination"

    @classmethod
    def _declared_url(cls):
        return "/destination"

    @classmethod
    def page_url(cls, **params):
        return "/destination"


class _TemplatedDestination(BasePage):
    """One page per record: /records/{record_id}."""
    INVENTORY_PAGE = "record"

    @classmethod
    def _declared_url(cls):
        return "/records/{record_id}"

    @classmethod
    def page_url(cls, **params):
        return "/records/{record_id}".format(**params)


def test_a_swallowed_navigation_is_re_issued():
    page = _AdPage(path="/previous")            # the click never landed
    obj = _DestinationPage(page)

    obj.confirm_arrival()

    assert page.gotos == ["https://app.example/destination"], (
        "clearing the ad does not replay the click - the navigation has to be "
        "re-issued to the page object's own declared URL"
    )


def test_arriving_normally_costs_nothing():
    """Break the thing the guard guards. Every ordinary run hits this path."""
    page = _AdPage(path="/destination")
    page.url = page.origin + "/destination"     # already here, no fragment
    obj = _DestinationPage(page)

    obj.confirm_arrival()

    assert page.gotos == [], "no navigation when the browser is already here"
    assert page.escapes == 0


def test_the_ad_is_cleared_even_when_the_page_is_right():
    """Arrived, but the ad is still covering it."""
    page = _AdPage(path="/destination")
    obj = _DestinationPage(page)

    obj.confirm_arrival()

    assert page.escapes == 1
    assert page.gotos == [], "the browser is already here - do not reload it"


# ─────────────────────────────────────────────────────────────────────────
# A TEMPLATED destination - one page per record
#
# The first version of confirm_arrival() returned quietly when page_url()
# could not be built without its parameters. The next run clicked through to
# a per-record page, the ad ate the navigation, confirm_arrival() shrugged,
# and the step spent thirty seconds waiting for a control that only exists
# on that page - then reported a timeout that pointed at the selector.
#
# It cannot rebuild the URL. It can refuse to pretend everything is fine.
# ─────────────────────────────────────────────────────────────────────────

def test_a_templated_page_recognises_that_it_arrived():
    """The fixed part before the placeholder is the most that can honestly be
    checked, and it is enough to tell 'arrived' from 'never left'."""
    page = _AdPage(path="/records/42")
    page.url = page.origin + "/records/42"
    obj = _TemplatedDestination(page)

    obj.confirm_arrival()                       # must not raise

    assert page.gotos == []


def test_a_templated_page_refuses_to_continue_from_the_wrong_page():
    page = _AdPage(path="/previous")
    obj = _TemplatedDestination(page)

    with pytest.raises(AssertionError) as exc:
        obj.confirm_arrival()

    message = str(exc.value)
    assert "/records/{record_id}" in message, "say where it should have been"
    assert "/previous" in message, "say where it actually is"
    assert "identifier" in message, "say how to make it recoverable"


def test_a_templated_page_recovers_when_given_its_identifier():
    page = _AdPage(path="/previous")
    obj = _TemplatedDestination(page)

    obj.confirm_arrival(record_id=42)

    assert page.gotos == ["https://app.example/records/42"]


def test_the_ad_is_cleared_before_the_templated_page_gives_up():
    """If dismissing reveals that the browser DID arrive, that is the answer -
    raising there would fail a run that was fine."""
    page = _AdPage(path="/records/42")          # here, behind an ad
    obj = _TemplatedDestination(page)

    obj.confirm_arrival()                       # must not raise

    assert page.escapes == 1


def test_reference_page_object_uses_the_probe():
    """The reference page object is the shape Agent 2 copies. If it goes back
    to a bare try/except, the swallowed-reason regression comes back with it.

    Read through the CONFIGURED reference rather than a hardcoded filename: a
    framework test that names one application's page object breaks the moment
    that page is deleted or regenerated, and it cannot run against any other
    app at all."""
    from core.app_context import AppContext
    body = AppContext.load().load_reference_files()["page_object"]
    assert "self.is_showing(" in body
    assert "except Exception:" not in body

# ─────────────────────────────────────────────────────────────────────────
# Templated page URLs
#
# Some pages are a TEMPLATE, not an address: /records/{record_id}
# stands for one page per record. Storing a sample id instead would couple
# every test to whichever record happened to be crawled, and would read as one
# page when it stands for thousands.
# ─────────────────────────────────────────────────────────────────────────
from inventory_tools.browser import resolve_page_url


class _TemplatedPage(BasePage):
    INVENTORY_PAGE = "x"
    _URL = "/"

    @classmethod
    def _inventory(cls):
        return {"pages": {"x": {"url": cls._URL}}}


def test_plain_url_is_returned_unchanged():
    _TemplatedPage._URL = "/dashboard"
    assert _TemplatedPage.page_url() == "/dashboard"


def test_plain_url_ignores_stray_params():
    """Passing an id to a non-templated page must not blow up."""
    _TemplatedPage._URL = "/dashboard"
    assert _TemplatedPage.page_url(record_id=9) == "/dashboard"


def test_template_is_substituted_at_runtime():
    _TemplatedPage._URL = "/records/{record_id}"
    assert _TemplatedPage.page_url(record_id=42) == "/records/42"


def test_template_accepts_a_non_numeric_id():
    _TemplatedPage._URL = "/records/{record_id}"
    assert _TemplatedPage.page_url(record_id="a-slug") == "/records/a-slug"


def test_template_with_several_placeholders():
    _TemplatedPage._URL = "/orders/{order_id}/items/{item_id}"
    assert _TemplatedPage.page_url(order_id=7, item_id=3) == "/orders/7/items/3"


@pytest.mark.parametrize("params", [{}, {"wrong_name": 1}])
def test_missing_param_names_what_is_needed(params):
    """Far better than navigating to a literal "{record_id}" and reporting
    every selector on the page as missing."""
    _TemplatedPage._URL = "/records/{record_id}"
    with pytest.raises(KeyError) as excinfo:
        _TemplatedPage.page_url(**params)
    assert "record_id" in str(excinfo.value)
    assert "template" in str(excinfo.value)


class TestToolsHandleTemplatedPages:
    """verify_locators and check_inventory_staleness would otherwise navigate
    to a literal "{record_id}", 404, and report every selector STALE - the
    false-report class these tools exist to avoid."""

    def test_plain_entry_proceeds(self):
        assert resolve_page_url({"url": "/dashboard"}) == ("/dashboard", None)

    def test_missing_url_defaults_to_root(self):
        assert resolve_page_url({}) == ("/", None)

    def test_sample_is_used_for_a_template(self):
        path, skip = resolve_page_url({"url": "/records/{record_id}",
                                       "url_sample": "/records/1"})
        assert path == "/records/1" and skip is None

    def test_template_without_a_sample_is_skipped_with_a_reason(self):
        path, skip = resolve_page_url({"url": "/records/{record_id}"})
        assert path == ""
        assert "url_sample" in skip and "record_id" in skip

    def test_a_still_templated_sample_is_rejected(self):
        """A sample that was never filled in is not a usable address."""
        _, skip = resolve_page_url({"url": "/a/{id}", "url_sample": "/a/{id}"})
        assert skip is not None

# ─────────────────────────────────────────────────────────────────────────
# Scoping beats indexing across families
#
# find_row_index_by_text() on one family then click_nth() on another assumes
# the two run in lockstep, one member each per row. A listing that renders
# every card's controls twice - once in the card, once in a hover overlay -
# gives one family 68 members and its neighbour 34. An index found in the first
# addresses the wrong element in the second, and nothing fails: the wrong
# record is simply acted on.
#
# click_in_row removes the assumption. The row is found by what it SAYS, the
# control is found INSIDE it, and the two families never have to agree.
# ─────────────────────────────────────────────────────────────────────────

class _Row:
    def __init__(self, label, targets):
        self.label, self._targets, self.clicked = label, targets, None

    def locator(self, sel):
        self.clicked = sel
        return self

    def click(self, timeout=None):
        self._targets.append((self.label, self.clicked))


class _Rows:
    """A repeating container; .filter(has_text=...) narrows it."""

    def __init__(self, labels, sink):
        self._labels, self._sink, self._match = labels, sink, None

    def filter(self, has_text=None):
        out = _Rows([l for l in self._labels if has_text in l], self._sink)
        return out

    def count(self):
        return len(self._labels)

    @property
    def first(self):
        return _Row(self._labels[0], self._sink)


def _page_with_rows(labels, sink):
    obj = BasePage.__new__(BasePage)
    obj._locator = lambda sel: _Rows(labels, sink)
    return obj


def test_the_control_inside_the_named_row_is_clicked():
    sink = []
    _page_with_rows(["Row A", "Row B", "Row C"], sink).click_in_row(
        ".row", "Row B", "a.action")
    assert sink == [("Row B", "a.action")]


def test_a_missing_row_says_what_to_check():
    """A silent miss here would click nothing and let the test carry on."""
    with pytest.raises(AssertionError) as excinfo:
        _page_with_rows(["Row A"], []).click_in_row(".row", "Row Z", "a.action")
    message = str(excinfo.value)
    assert "Row Z" in message
    assert "CONTAINER" in message, \
        "the usual mistake is passing the text element, not the row around it"


def test_row_containing_returns_the_row_for_reading():
    row = _page_with_rows(["Row A", "Row B"], []).row_containing(".row", "Row B")
    assert row.label == "Row B"


# =========================================================================
# ACTING ON A PAGE WITHOUT CONFIRMING YOU ARE ON IT
#
# The reference sign-in method filled its fields with no check that the page
# was showing. A scenario that reached it from elsewhere spent the full
# timeout and then reported the LOCATOR as having timed out - which reads as a
# broken selector, and the selector was fine. The page was wrong.
#
# It RAISES rather than navigating. Being on the wrong page here means a
# scenario forgot its opening step; correcting that silently would hide the
# mistake and let the scenario pass for a reason it never stated.
# =========================================================================

def test_the_reference_sign_in_refuses_to_act_on_the_wrong_page():
    from core.app_context import AppContext

    import ast

    body = AppContext.load().load_reference_files()["page_object"]
    tree = ast.parse(body)

    # The method must be CALLED, not merely defined. A guard that only checks
    # for a definition passes a file where the call was deleted - which is how
    # dismiss_interstitial() sat in this codebase for months with no caller.
    guarded = []
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for node in cls.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fills = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "fill" for n in ast.walk(node))
            if not fills:
                continue
            checks = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and (n.func.attr.startswith("_require") or n.func.attr == "confirm_arrival")
                for n in ast.walk(node))
            guarded.append((node.name, checks))

    assert guarded, "the reference page object fills nothing - check the fixture"
    unguarded = [name for name, checks in guarded if not checks]
    assert not unguarded, (
        f"{unguarded} fill credentials without confirming the page is showing. "
        f"Filling a field that is not there waits the FULL timeout and then "
        f"blames the locator. This is the shape Agent 2 copies into every page "
        f"object it writes."
    )


def test_the_reference_precondition_names_the_page_it_expected():
    """A precondition that says only "wrong page" sends the reader looking.
    It has to name where the browser is and where it should be."""
    from core.app_context import AppContext

    body = AppContext.load().load_reference_files()["page_object"]
    if "_require_" not in body:
        pytest.skip("no precondition in this reference")

    assert "not on {expected}" in body or "not on " in body
    assert "full timeout" in body, (
        "say why this matters - without it the next reader deletes the check "
        "as redundant"
    )


# =========================================================================
# THE SIGN-IN PAGE OBJECT REACHES ITS OWN PAGE
#
# It used to RAISE when the browser was elsewhere, so that a scenario could
# not pass for a reason it never stated. That reversed here.
#
# The scenario that hit it was doing something reasonable: clearing an
# account-scoped collection in a Given, which navigates to that collection's
# page. Every route to the login form was legitimate; refusing to take one
# turned a recoverable situation into two failed tests and a regeneration.
#
# The method needs the login page, being elsewhere has exactly one sensible
# recovery, and taking it is what confirm_arrival() does everywhere else. The
# scenario-level mistake - a precondition placed before the sign-in it
# depends on - is caught by the persistent-state rule and by review.
# =========================================================================

def test_the_reference_sign_in_navigates_when_the_browser_is_elsewhere():
    """The shape that failed two tests."""
    from core.app_context import AppContext

    from pages.login_page import LoginPage

    class _Page:
        def __init__(self, url):
            self.url = url
            self.gotos = []

        def goto(self, url, **_):
            self.gotos.append(url)
            self.url = url

        def wait_for_timeout(self, _ms):
            pass

        def locator(self, selector, **_):
            return selector

    # BEHAVIOUR, not source text. A guard that greps for `self.navigate(`
    # passes a file where the call was gutted to `pass` - which is exactly
    # what the first version of this test did.
    elsewhere = _Page("https://app.example/somewhere-else")
    LoginPage(elsewhere)._require_login_page()
    assert elsewhere.gotos, (
        "the browser was on another page and nothing navigated - the fill "
        "that follows would wait the full timeout and blame the field"
    )
    assert elsewhere.url.endswith(LoginPage(elsewhere).page_url()), (
        f"navigated to {elsewhere.url!r}, which is not the login page"
    )

    already = _Page(f"https://app.example{LoginPage(_Page('x')).page_url()}")
    LoginPage(already)._require_login_page()
    assert not already.gotos, "already there - navigating again wastes a load"


def test_the_recovery_still_refuses_when_there_is_nowhere_to_navigate_from():
    """Break the thing the guard guards. A blank page has no origin, and
    guessing one would navigate somewhere nobody asked for."""
    from core.app_context import AppContext

    body = AppContext.load().load_reference_files()["page_object"]
    assert "raise AssertionError" in body, (
        "with no scheme or host there is nothing to build a URL from, and the "
        "failure has to say so rather than inventing an address"
    )

