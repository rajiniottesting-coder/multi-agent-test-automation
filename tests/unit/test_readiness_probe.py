"""A readiness probe must hold in EVERY state its page can be in.

WHAT HAPPENED
    Three tests failed with:

        SomePage.is_showing('text=<the unfiltered heading>') is False
        at /listing?search=<a term>

    The listing's heading changes once a search runs, so a probe built on the
    unsearched heading reports "not loaded" for a page that had loaded and
    searched perfectly well.

WHY THE GENERATOR COULD NOT HAVE GOT THIS RIGHT
    Both headings were in the inventory. The state-dependent one was declared
    `conditional`, which correctly means "do not expect this on page load", so
    for a readiness probe the model reasonably avoided it and used the other.
    It followed the rules exactly and still produced a broken probe, because
    nothing in the inventory said which element survives every state.

    Only someone who has seen the page in each state knows that. `readiness`
    is where they write it down, and this validator makes it binding - the
    inventory note alone was advisory, and advisory was not enough.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import validate_readiness_probe

_INV = {"pages": {"widgets": {
    "elements": {"search_box": "#q", "list_heading": "text=All Widgets"},
    "readiness": "search_box",
}}}


def _page(body: str, cls: str = "WidgetsPage", page: str = "widgets"):
    return SimpleNamespace(
        file_path="pages/widgets_page.py",
        content=f'class {cls}(BasePage):\n    INVENTORY_PAGE = "{page}"\n{body}',
    )


def test_a_probe_on_the_wrong_element_is_rejected():
    errors = validate_readiness_probe(
        [_page('    def is_loaded(self) -> bool:\n'
               '        return self.is_showing(self.sel("list_heading"))\n')],
        inventory=_INV)
    assert len(errors) == 1
    assert "readiness = 'search_box'" in errors[0]


def test_the_message_says_what_to_write():
    errors = validate_readiness_probe(
        [_page('    def is_loaded(self) -> bool:\n'
               '        return self.is_showing(self.sel("list_heading"))\n')],
        inventory=_INV)
    assert 'self.sel("search_box")' in errors[0], \
        "a rejection the repair loop cannot act on is worse than none"
    assert "EVERY state" in errors[0]


def test_the_declared_element_passes():
    assert validate_readiness_probe(
        [_page('    def is_loaded(self) -> bool:\n'
               '        return self.is_showing(self.sel("search_box"))\n')],
        inventory=_INV) == []


def test_probing_the_declared_element_among_others_passes():
    """Additional checks are the page object's business - the requirement is
    that the declared anchor is among them."""
    assert validate_readiness_probe(
        [_page('    def is_loaded(self) -> bool:\n'
               '        return (self.is_showing(self.sel("search_box"))\n'
               '                and self.is_showing(self.sel("list_heading")))\n')],
        inventory=_INV) == []


def test_a_page_with_no_declared_readiness_is_not_policed():
    """Most pages have one obvious anchor and need no ceremony. The check fires
    only where a human has said the choice matters."""
    inv = {"pages": {"widgets": {"elements": {"a": "#a"}}}}
    assert validate_readiness_probe(
        [_page('    def is_loaded(self) -> bool:\n'
               '        return self.is_showing(self.sel("a"))\n')],
        inventory=inv) == []


def test_a_page_object_without_is_loaded_is_not_policed():
    assert validate_readiness_probe(
        [_page('    def go(self) -> None:\n        pass\n')], inventory=_INV) == []


@pytest.mark.parametrize("content", [None, "", "def (((", 123])
def test_unusable_content_never_raises(content):
    assert validate_readiness_probe(
        [SimpleNamespace(file_path="pages/x_page.py", content=content)],
        inventory=_INV) == []


def test_no_inventory_means_no_opinion():
    assert validate_readiness_probe(
        [_page('    def is_loaded(self) -> bool:\n'
               '        return self.is_showing(self.sel("list_heading"))\n')],
        inventory={}) == []


def test_the_committed_page_objects_satisfy_their_declared_readiness():
    """Applied to whatever pages/ holds, so a hand-edit or a merge cannot
    reintroduce the mismatch without the suite noticing."""
    import json
    from core.app_context import AppContext

    root = Path(__file__).resolve().parents[2]
    inv_path = AppContext.load().inventory_path()
    if not inv_path.is_file():
        pytest.skip("no inventory configured")
    inventory = json.loads(inv_path.read_text(encoding="utf-8"))

    files = [
        SimpleNamespace(file_path=f"pages/{f.name}",
                        content=f.read_text(encoding="utf-8"))
        for f in sorted((root / "pages").glob("*_page.py"))
        if f.name != "base_page.py"
    ]
    if not files:
        pytest.skip("no page objects committed yet")
    assert validate_readiness_probe(files, inventory=inventory) == []