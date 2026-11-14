"""A yes/no predicate over a table row is not a misnamed reader: it is
accepted, while a reader returning row text under a field name is still
refused.
"""

from __future__ import annotations

from pathlib import Path
import pytest


ROOT = Path(__file__).resolve().parents[2]


def _rows_page(body: str):
    from types import SimpleNamespace as NS
    return NS(file_path="pages/rows_page.py", content=(
        "from pages.base_page import BasePage\n\n\nclass RowsPage(BasePage):\n"
        '    INVENTORY_PAGE = "rows_demo"\n\n' + body))


@pytest.fixture
def rows_inventory(monkeypatch):
    import validators.method_resolution_validator as v
    monkeypatch.setattr(v, "_load_configured_inventory", lambda root: {"pages": {"rows_demo": {
        "elements": {"item_rows": "tr.item"}, "multi_match": ["item_rows"],
        "row_family": "item_rows"}}})
    return v


def test_a_predicate_reading_a_row_is_accepted(rows_inventory):
    body = ('    def has_item_with_cost(self, name: str, cost: str) -> bool:\n'
            '        text = self.get_text(self.sel("item_rows"))\n'
            '        return name in text and cost in text\n')
    assert rows_inventory.validate_readers_return_what_they_name([_rows_page(body)], ROOT) == []


def test_a_reader_returning_row_text_under_a_field_name_is_still_refused(rows_inventory):
    body = ('    def get_item_cost(self) -> str:\n'
            '        return self.get_text(self.sel("item_rows"))\n')
    (err,) = rows_inventory.validate_readers_return_what_they_name([_rows_page(body)], ROOT)
    assert err.startswith("Reader naming error") and "cost" in err
