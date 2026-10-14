"""click_in_row clicks the VISIBLE copy of a control drawn twice in one row.

Found in validation story A3 (PR #183): the listing draws each card's
"Add to cart" in the card and again in a hover overlay. click_in_row scoped
to the right card, but the control still matched 2 elements and Playwright's
strict mode refused the click - the new test failed for a reason unrelated
to the story. Fake locators; no browser, no application names.
"""
from unittest.mock import MagicMock

import pages.base_page as bp


class FakeLoc:
    def __init__(self, visibles, name="target"):
        self.visibles, self.name = visibles, name
        self.clicked = None

    def count(self):
        return len(self.visibles)

    def nth(self, i):
        m = FakeLoc([self.visibles[i]], f"{self.name}[{i}]")
        m.parent = self
        return m

    @property
    def first(self):
        return self.nth(0) if self.visibles else self

    def is_visible(self):
        return bool(self.visibles and self.visibles[0])


def test_a_single_match_is_left_alone():
    t = FakeLoc([True])
    assert bp.BasePage._visible_member(t) is t


def test_no_match_is_left_alone_so_the_click_waits_and_reports():
    t = FakeLoc([])
    assert bp.BasePage._visible_member(t) is t


def test_the_visible_copy_is_chosen():
    t = FakeLoc([False, True])
    assert bp.BasePage._visible_member(t).name == "target[1]"
    t = FakeLoc([True, False])
    assert bp.BasePage._visible_member(t).name == "target[0]"


def test_none_visible_falls_back_to_the_first_so_the_click_waits():
    t = FakeLoc([False, False])
    assert bp.BasePage._visible_member(t).name == "target[0]"


def test_click_in_row_clicks_through_the_visible_member(monkeypatch):
    clicked = []
    target = MagicMock()
    target.count.return_value = 2
    hidden, shown = MagicMock(), MagicMock()
    hidden.is_visible.return_value, shown.is_visible.return_value = False, True
    shown.click.side_effect = lambda **k: clicked.append("shown")
    hidden.click.side_effect = lambda **k: clicked.append("hidden")
    target.nth.side_effect = [hidden, shown]
    row = MagicMock()
    row.count.return_value = 1
    row.first.locator.return_value = target
    rows = MagicMock()
    rows.filter.return_value = row
    page = bp.BasePage.__new__(bp.BasePage)
    monkeypatch.setattr(page, "_locator", lambda sel: rows, raising=False)
    monkeypatch.setattr(page, "_default_timeout_ms", lambda: 1000, raising=False)
    page.click_in_row("<row family>", "Alpha", "<control>")
    assert clicked == ["shown"]
