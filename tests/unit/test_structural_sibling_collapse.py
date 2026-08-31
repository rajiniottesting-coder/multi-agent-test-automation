"""Fifty rows are one widget, not fifty elements.

WHAT HAPPENED
    A crawl of a table produced fifty keys like `0455_alaa_ayman_row` and
    `0387_beth_cole_row`, each a structural path to one row, plus `1_button`
    through `5_button` for the pager.

    `collapse_indexed_families` groups by NAME STEM - `row`, `row_2`, `row_3`
    - so it catches a widget whose members the ranker could not tell apart and
    misses the commoner case entirely: when each member HAS distinguishing
    text, every one gets a different name and a different stem, and the
    collapse never sees a family at all.

    Those keys are worse than useless. Each is named after a record someone
    else will edit or delete, so it goes stale on its own; and fifty of them
    cannot answer "how many rows are there", which ONE family key answers with
    get_count(). On a shared demo the record count changed twice in the few
    minutes it took to look at one page.

    The signal is REPETITION, not uniqueness. Making these keys MORE specific -
    adding attributes, pinning to a neighbour - pins them harder to data that
    is about to change.
"""
import pytest

from inventory_tools.introspect import (
    collapse_structural_siblings,
    _structural_signature,
    _family_handle,
    _common_suffix_name,
)


def _rows(n: int, prefix="row"):
    """N sibling paths differing only in position, named after their data."""
    return {
        f"{1000 + i}_person_{i}_{prefix}": {
            "selector": f"#app > div:nth-of-type(1) > div > div:nth-of-type({i + 6}) > div"
        }
        for i in range(n)
    }


def test_siblings_named_after_data_collapse_to_one_key():
    elements = _rows(50)
    out, families, report, _ = collapse_structural_siblings(elements)
    assert len(out) == 1, f"50 rows should be 1 family, got {len(out)}"
    assert families == ["rows"]
    assert report["rows"]["count"] == 50


def test_the_handle_widens_ONLY_where_the_members_differ():
    """Two failure modes, opposite directions.

    Too narrow - a handle matching only the first member - gives a key called
    `rows` that silently resolves to one element.

    Too wide is what shipped first: stripping EVERY `:nth-of-type` turned a
    ten-deep path into `#app > div > div > ... > div`, which matches most of
    the page rather than the seven rows it came from. Every ancestor the
    members share is what makes the handle mean "these rows" and not "any
    div", so only the varying segment may be widened.
    """
    out, families, _, _ = collapse_structural_siblings(_rows(5))
    handle = out[families[0]]["selector"]

    assert "div:nth-of-type(1)" in handle, \
        "shared ancestors must stay pinned or the handle matches the page"
    assert "div:nth-of-type(6)" not in handle, \
        "the varying segment must be widened or it matches one member"


def test_members_at_different_depths_are_not_one_widget():
    """Nothing sensible spans them, and a handle built anyway would be wrong."""
    elements = {
        "a_row": {"selector": "#app > div:nth-of-type(1) > p"},
        "b_row": {"selector": "#app > div > div:nth-of-type(2) > p"},
        "c_row": {"selector": "#app > div > div > div:nth-of-type(3) > p"},
    }
    out, families, _, _ = collapse_structural_siblings(elements)
    assert families == []
    assert len(out) == 3


def test_the_family_is_named_from_what_the_members_SHARE():
    """Members named after data have nothing in common at the front and the
    meaningful noun at the back."""
    assert _common_suffix_name(
        ["0455_alaa_ayman_row", "0387_beth_cole_row", "0312_a8_dco_row"]) == "row"


def test_nothing_is_deleted_silently():
    """The members are listed so a wrong collapse can be undone."""
    _, families, report, _ = collapse_structural_siblings(_rows(50))
    entry = report[families[0]]
    assert entry["was"], "the original names must be recorded"
    assert "get_count()" in entry["note"], \
        "say what the family is FOR, or a reader restores the fifty keys"


# ── what must NOT be collapsed ───────────────────────────────────────────

def test_a_family_with_no_shared_handle_is_reported_not_invented():
    """`role=button[name='1']` ... `[name='5']`: the varying part is the
    element's NAME, not its position, so no widening matches them all.
    Emitting one anyway gives a key called `buttons` that resolves to a single
    element - passing every check while meaning something false."""
    elements = {f"{i}_button": {"selector": f"role=button[name='{i}']"}
                for i in range(1, 6)}
    out, families, _, unhandled = collapse_structural_siblings(elements)
    assert families == [], "nothing may be collapsed without a real handle"
    assert len(out) == 5, "the members must survive untouched"
    assert unhandled, "and the reader must be told they are one widget"
    assert "multi_match" in str(unhandled), "say what to do about it"


def test_genuinely_different_elements_are_left_alone():
    elements = {
        "primary_button": {"selector": "#primary"},
        "secondary_button": {"selector": "#secondary"},
        "total_label": {"selector": "text=Total"},
        "filter_field": {"selector": "input[placeholder='Filter']"},
    }
    out, families, _, _ = collapse_structural_siblings(elements)
    assert out == elements
    assert families == []


def test_two_similar_siblings_are_a_pair_not_a_family():
    """Below the threshold. Two matching things are usually a genuine pair."""
    out, families, _, _ = collapse_structural_siblings(_rows(2))
    assert families == []
    assert len(out) == 2


def test_elements_without_a_digit_are_never_grouped():
    elements = {"header": {"selector": "h1.title"},
                "footer": {"selector": "div.footer"},
                "nav": {"selector": "nav.main"}}
    out, families, _, _ = collapse_structural_siblings(elements)
    assert out == elements and families == []


def test_members_whose_names_share_nothing_are_left_alone():
    """A family key nobody can read is worse than several honest ones."""
    elements = {
        "alpha": {"selector": "#app > div:nth-of-type(1) > p"},
        "beta": {"selector": "#app > div:nth-of-type(2) > p"},
        "gamma": {"selector": "#app > div:nth-of-type(3) > p"},
    }
    out, families, _, _ = collapse_structural_siblings(elements)
    assert families == [], "no shared name means no sensible family key"
    assert len(out) == 3


@pytest.mark.parametrize("elements", [{}, {"a": {}}, {"a": {"selector": ""}}])
def test_degenerate_input_never_raises(elements):
    out, families, report, unhandled = collapse_structural_siblings(elements)
    assert families == [] and report == {} and unhandled == {}


def test_a_collapsed_key_never_overwrites_a_real_one():
    """If the app already has an element called `rows`, the family must not
    silently replace it."""
    elements = _rows(5)
    elements["rows"] = {"selector": "#a-real-element"}
    out, families, _, _ = collapse_structural_siblings(elements)
    assert out["rows"]["selector"] == "#a-real-element"
    assert families and families[0] != "rows"


def test_the_signature_ignores_integers_only():
    assert _structural_signature("div:nth-of-type(6) > a") == \
           _structural_signature("div:nth-of-type(7) > a")
    assert _structural_signature("div.alpha") != _structural_signature("div.beta")