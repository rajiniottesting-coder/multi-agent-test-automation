"""Unit tests for the BasePage helper-signature injection.

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