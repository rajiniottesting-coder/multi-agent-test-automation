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


def _cls(*methods: str, name: str = "ListingPage") -> str:
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
    ("record_name", "record_price"),
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
    src = _cls("filter_by_brand") + "\n" + _cls("filter_products_by_brand", name="BasketPage")
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


# ─────────────────────────────────────────────────────────────────────────
# Edge cases — the gate must never take down a story for a reason unrelated
# to the code it was checking.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("content", [
    None,               # an upstream fetch returned nothing
    b"class P: pass",   # bytes rather than str
    123,                # wrong type entirely
    "",                 # empty
    "   \n  ",          # whitespace only
    "\x00\x00",         # null bytes
    "def (((",          # unparseable
])
def test_unusable_content_never_raises(content):
    """`content=None` raised TypeError before this: SyntaxError alone does not
    cover a non-string, and a gate that dies on a failed fetch fails the story
    for the wrong reason."""
    assert validate_no_duplicate_page_object_methods(
        [SimpleNamespace(file_path="pages/x_page.py", content=content)]) == []


@pytest.mark.parametrize("src,flagged", [
    ("", False),
    ("def free_function(): pass\n", False),                       # no class
    ("class P:\n    pass\n", False),                              # no methods
    ("class P:\n    def only_one(self): pass\n", False),
    ("class P:\n    def _a_b(self): pass\n    def _b_a(self): pass\n", False),   # private
    ("class P:\n    def __init__(self): pass\n    def __repr__(self): pass\n", False),
    ("class P:\n    async def load_page(self): pass\n"
     "    async def load_the_page(self): pass\n", True),          # async counts
    ("class P:\n    @property\n    def total_price(self): pass\n"
     "    @property\n    def the_total_price(self): pass\n", True),  # decorated counts
    ("class P:\n    def remove_item(self): pass\n    def remove_the_item(self): pass\n"
     "    def remove_an_item(self): pass\n", True),               # three-way
    ("class P:\n    def the_page(self): pass\n    def a_page(self): pass\n", False),  # all filler
])
def test_structural_edge_cases(src, flagged):
    assert bool(find_redundant_methods(src, "products")) is flagged


def test_methods_in_a_NESTED_class_are_not_compared_with_the_outer_one():
    src = ("class Outer:\n"
           "    class Inner:\n"
           "        def go_home(self): pass\n"
           "    def go_home(self): pass\n")
    assert find_redundant_methods(src) == []

# ─────────────────────────────────────────────────────────────────────────
# The same rule, pointed at what is COMMITTED
#
# Everything above tests the validator against synthetic files. That covers
# the generation gate - but a gate only guards what passes THROUGH it, and the
# case this rule exists for never does.
#
# Two stories touching one page object both branch from main, so neither sees
# the other. Story A adds filter_by_brand(), story B adds
# filter_products_by_brand(). If the additions land far enough apart, git
# merges both cleanly: nothing conflicts, nothing fails, and the page object
# quietly grows two methods for one behaviour. The validator never runs on the
# merged result, because merging is not generating.
#
# This is the same function applied to whatever pages/ actually holds, so a bad
# merge fails CI on main. It is not an eleventh validator - it is the tenth,
# aimed at a second target.
# ─────────────────────────────────────────────────────────────────────────

def test_no_committed_page_object_holds_duplicate_methods():
    from pathlib import Path

    pages_dir = Path(__file__).resolve().parents[2] / "pages"
    files = [f for f in sorted(pages_dir.glob("*_page.py"))
             if f.name != "base_page.py"]
    if not files:
        import pytest as _pytest
        _pytest.skip("no page objects committed yet - Agent 2 has not run")

    errors = validate_no_duplicate_page_object_methods([
        SimpleNamespace(file_path=f"pages/{f.name}",
                        content=f.read_text(encoding="utf-8"))
        for f in files
    ])
    assert not errors, (
        "a committed page object holds two methods meaning the same thing. "
        "This is what a clean merge between two concurrent branches produces: "
        "neither could see the other, so both added their own name for one "
        "behaviour. Keep whichever name the existing step definitions call and "
        "delete the other.\n  " + "\n  ".join(errors))