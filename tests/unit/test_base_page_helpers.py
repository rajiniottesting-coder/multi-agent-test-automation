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


def test_reference_page_object_uses_the_probe():
    """home_page.is_loaded() is the shape Agent 2 copies. If it goes back to a
    bare try/except the swallowed-reason regression comes back with it.

    Named through the configured reference rather than a fixed filename would
    be better still, but the landing page is the one every app has."""
    src = Path(__file__).resolve().parents[2] / "pages" / "home_page.py"
    body = src.read_text(encoding="utf-8")
    assert "self.is_showing(" in body
    assert "except Exception:" not in body

# ─────────────────────────────────────────────────────────────────────────
# Templated page URLs
#
# Some pages are a TEMPLATE, not an address: /product_details/{product_id}
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
    _TemplatedPage._URL = "/view_cart"
    assert _TemplatedPage.page_url() == "/view_cart"


def test_plain_url_ignores_stray_params():
    """Passing an id to a non-templated page must not blow up."""
    _TemplatedPage._URL = "/view_cart"
    assert _TemplatedPage.page_url(product_id=9) == "/view_cart"


def test_template_is_substituted_at_runtime():
    _TemplatedPage._URL = "/product_details/{product_id}"
    assert _TemplatedPage.page_url(product_id=42) == "/product_details/42"


def test_template_accepts_a_non_numeric_id():
    _TemplatedPage._URL = "/product_details/{product_id}"
    assert _TemplatedPage.page_url(product_id="blue-top") == "/product_details/blue-top"


def test_template_with_several_placeholders():
    _TemplatedPage._URL = "/orders/{order_id}/items/{item_id}"
    assert _TemplatedPage.page_url(order_id=7, item_id=3) == "/orders/7/items/3"


@pytest.mark.parametrize("params", [{}, {"wrong_name": 1}])
def test_missing_param_names_what_is_needed(params):
    """Far better than navigating to a literal "{product_id}" and reporting
    every selector on the page as missing."""
    _TemplatedPage._URL = "/product_details/{product_id}"
    with pytest.raises(KeyError) as excinfo:
        _TemplatedPage.page_url(**params)
    assert "product_id" in str(excinfo.value)
    assert "template" in str(excinfo.value)


class TestToolsHandleTemplatedPages:
    """verify_locators and check_inventory_staleness would otherwise navigate
    to a literal "{product_id}", 404, and report every selector STALE - the
    false-report class these tools exist to avoid."""

    def test_plain_entry_proceeds(self):
        assert resolve_page_url({"url": "/view_cart"}) == ("/view_cart", None)

    def test_missing_url_defaults_to_root(self):
        assert resolve_page_url({}) == ("/", None)

    def test_sample_is_used_for_a_template(self):
        path, skip = resolve_page_url({"url": "/product_details/{product_id}",
                                       "url_sample": "/product_details/1"})
        assert path == "/product_details/1" and skip is None

    def test_template_without_a_sample_is_skipped_with_a_reason(self):
        path, skip = resolve_page_url({"url": "/product_details/{product_id}"})
        assert path == ""
        assert "url_sample" in skip and "product_id" in skip

    def test_a_still_templated_sample_is_rejected(self):
        """A sample that was never filled in is not a usable address."""
        _, skip = resolve_page_url({"url": "/a/{id}", "url_sample": "/a/{id}"})
        assert skip is not None