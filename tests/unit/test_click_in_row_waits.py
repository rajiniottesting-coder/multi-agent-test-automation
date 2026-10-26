"""click_in_row waits for the row before calling it missing.

PR #215's Agent 4 run (26 Oct 2026): a scenario clicked "View Cart" and the
very next step deleted a product's row with click_in_row(). It counted the rows
at once - before the cart page had drawn them - found none, and failed, while
other scenarios' waiting readers found the same row. Counting is a snapshot;
the first row action after a navigation has to wait.
Generic names only; no browser.
"""
import pages.base_page as bp


class _Target:
    def __init__(self, sink):
        self.sink = sink

    def count(self):
        return 1

    def click(self, timeout=None):
        self.sink.append("clicked")


class _First:
    def __init__(self, rows):
        self.rows = rows

    def wait_for(self, state=None, timeout=None):
        self.rows.waited.append((state, timeout))
        self.rows.drawn = self.rows.will_draw          # the page finished rendering

    def locator(self, sel):
        return _Target(self.rows.sink)


class _Rows:
    def __init__(self, will_draw):
        self.drawn, self.will_draw, self.waited, self.sink = False, will_draw, [], []

    def filter(self, has_text=None):
        return self

    def count(self):
        return 1 if self.drawn else 0

    @property
    def first(self):
        return _First(self)


def _page(rows):
    page = bp.BasePage.__new__(bp.BasePage)
    page._locator = lambda sel: rows
    page._default_timeout_ms = lambda: 1234
    return page


def test_a_row_drawn_after_the_first_count_is_clicked():
    rows = _Rows(will_draw=True)
    _page(rows).click_in_row("<rows>", "Alpha", "<control>")
    assert rows.waited == [("attached", 1234)]
    assert rows.sink == ["clicked"]


def test_a_row_that_never_appears_still_fails_with_the_message():
    rows = _Rows(will_draw=False)
    try:
        _page(rows).click_in_row("<rows>", "Alpha", "<control>")
    except AssertionError as e:
        assert "Alpha" in str(e) and "CONTAINER" in str(e)
    else:
        raise AssertionError("a missing row must fail")
    assert rows.waited and rows.sink == []


def test_a_row_already_there_is_clicked_without_waiting():
    rows = _Rows(will_draw=True)
    rows.drawn = True
    _page(rows).click_in_row("<rows>", "Alpha", "<control>")
    assert rows.waited == [] and rows.sink == ["clicked"]
