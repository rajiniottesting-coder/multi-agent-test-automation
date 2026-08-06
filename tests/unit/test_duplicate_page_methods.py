"""Redundant page-object methods, and the branch-aware read that reduces them.

THE PROBLEM
    Two stories touching one page object both branch from `main`, so neither
    can see the other's work. Story A adds `filter_by_brand()`, story B adds
    `filter_products_by_brand()`. If the additions land far enough apart, git
    merges both cleanly — nothing fails, and the page object quietly grows two
    methods for one behaviour.

    `validate_method_resolution` cannot catch it: that checks a called method
    EXISTS, not that two methods are the same idea twice.

THREE DEFENCES, in the order they apply
    1. Sequence stories that touch the same page (documented in GUIDE.md).
    2. Read the story's own branch, so a RE-RUN sees its own earlier work
       instead of renaming it.
    3. This validator, at the generation gate, where a human is already
       looking at the diff.
"""
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import (
    find_redundant_methods,
    validate_no_duplicate_page_object_methods,
)


def _cls(*methods: str, name: str = "ProductsPage") -> str:
    body = "\n".join(f"    def {m}(self): pass" for m in methods)
    return f"class {name}(BasePage):\n    INVENTORY_PAGE = 'products'\n{body}\n"


# ── what must be flagged ────────────────────────────────────────────────

def test_the_concurrency_case_is_caught():
    """The exact shape two independent branches produce."""
    pairs = find_redundant_methods(
        _cls("filter_by_brand", "filter_products_by_brand"), "products")
    assert pairs == [("filter_by_brand", "filter_products_by_brand")]


def test_filler_words_do_not_hide_a_duplicate():
    assert find_redundant_methods(_cls("remove_product", "remove_the_product"))


def test_word_order_does_not_hide_a_duplicate():
    """`by_brand_filter` and `filter_by_brand` are one method twice."""
    assert find_redundant_methods(_cls("filter_by_brand", "brand_filter"))


# ── what must NOT be flagged ────────────────────────────────────────────

@pytest.mark.parametrize("methods", [
    ("set_quantity", "get_quantity"),      # mutator vs accessor
    ("add_to_cart", "remove_from_cart"),   # opposite verbs
    ("is_loaded", "open"),
    ("product_name", "product_price"),
    ("submit_review", "write_review_link_is_visible"),
])
def test_genuinely_different_methods_pass(methods):
    """A false positive here costs a repair attempt on correct code, so the
    check must stay narrow. `get` and `set` are NOT stopwords precisely
    because they distinguish an accessor from a mutator."""
    assert find_redundant_methods(_cls(*methods), "products") == []


def test_private_methods_are_ignored():
    assert find_redundant_methods(_cls("_filter_by_brand", "filter_by_brand")) == []


def test_methods_in_different_classes_are_not_compared():
    src = _cls("filter_by_brand") + "\n" + _cls("filter_products_by_brand", name="CartPage")
    assert find_redundant_methods(src) == []


# ── the gate ────────────────────────────────────────────────────────────

def test_the_gate_reports_the_pair_and_says_which_to_keep():
    errors = validate_no_duplicate_page_object_methods(
        [SimpleNamespace(file_path="pages/products_page.py",
                         content=_cls("filter_by_brand", "filter_products_by_brand"))])
    assert len(errors) == 1
    assert "filter_by_brand" in errors[0] and "filter_products_by_brand" in errors[0]
    assert "existing step definitions already" in errors[0], \
        "the message must say WHICH name to keep, not just that two exist"


def test_base_page_is_exempt():
    """75 general-purpose helpers legitimately overlap in wording."""
    assert validate_no_duplicate_page_object_methods(
        [SimpleNamespace(file_path="pages/base_page.py",
                         content=_cls("fill_field", "fill_the_field"))]) == []


def test_non_page_object_files_are_ignored():
    assert validate_no_duplicate_page_object_methods(
        [SimpleNamespace(file_path="tests/step_defs/test_x.py",
                         content=_cls("filter_by_brand", "filter_products_by_brand"))]) == []


def test_an_unparseable_file_does_not_crash_the_gate():
    """A half-written file is the repair loop's problem, not this check's."""
    assert validate_no_duplicate_page_object_methods(
        [SimpleNamespace(file_path="pages/x_page.py", content="def (((")]) == []


def test_no_generated_files_is_safe():
    assert validate_no_duplicate_page_object_methods([]) == []
    assert validate_no_duplicate_page_object_methods(None) == []