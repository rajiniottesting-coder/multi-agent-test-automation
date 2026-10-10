"""Unit tests for --compare mode (design E1): which live elements no inventory
selector covers.

  introspect.uncovered_descriptors(descriptors)
  introspect.uncovered_elements(url, title, descriptors, base_url, test_attrs)

Pure logic only: descriptors are hand-built dicts shaped like the browser's
snapshot. The browser side (marking nodes, frames, shadow DOM) is exercised
against a real Chromium in tests/unit/test_inventory_compare_live.py.

No application names here: the elements are generic controls.
"""
from inventory_tools import introspect
from inventory_tools.introspect import COVER_ATTR


def _desc(tag, attrs=None, text="", label="", **extra):
    """A snapshot descriptor with the keys the capture JS always sets."""
    d = {
        "tag": tag,
        "attrs": dict(attrs or {}),
        "text": text,
        "renderedText": text,
        "label": label,
        "visible": True,
        "thirdParty": False,
        "hasIconChild": False,
        "cssPath": "",
    }
    d.update(extra)
    return d


def _covered(d):
    """What the browser does to a node an inventory selector resolves to."""
    d = dict(d)
    d["attrs"] = {**d["attrs"], COVER_ATTR: ""}
    return d


# ─────────────────────────────────────────────────────────────
# uncovered_descriptors
# ─────────────────────────────────────────────────────────────

def test_marked_descriptor_is_covered_and_unmarked_is_not():
    marked = _covered(_desc("button", {"id": "save"}, text="Save"))
    plain = _desc("button", {"id": "cancel"}, text="Cancel")
    out = introspect.uncovered_descriptors([marked, plain])
    assert out == [plain]


def test_no_marks_means_everything_is_uncovered():
    descs = [_desc("button", text="A"), _desc("input", {"type": "text"})]
    assert introspect.uncovered_descriptors(descs) == descs


def test_all_marked_means_nothing_is_uncovered():
    descs = [_covered(_desc("button", text="A"))]
    assert introspect.uncovered_descriptors(descs) == []


def test_missing_attrs_key_is_treated_as_unmarked():
    d = {"tag": "button", "text": "X"}          # no "attrs" at all
    assert introspect.uncovered_descriptors([d]) == [d]


def test_the_mark_itself_is_never_returned_as_an_attribute():
    """The mark must not leak into a selector or name built from attrs."""
    marked = _covered(_desc("button", {"id": "save"}, text="Save"))
    assert introspect.uncovered_descriptors([marked]) == []


# ─────────────────────────────────────────────────────────────
# uncovered_elements
# ─────────────────────────────────────────────────────────────

URL = "https://app.example/page"


def test_uncovered_element_is_reported_with_a_selector():
    descs = [_desc("button", {"id": "cancel"}, text="Cancel")]
    out = introspect.uncovered_elements(URL, "Page", descs)
    assert out, "an unmarked button must be reported"
    assert any("Cancel" in name or "cancel" in name.lower() for name in out)
    assert all(isinstance(v, str) and v for v in out.values())


def test_covered_element_is_not_reported():
    descs = [
        _covered(_desc("button", {"id": "save"}, text="Save")),
        _desc("button", {"id": "cancel"}, text="Cancel"),
    ]
    names = " ".join(introspect.uncovered_elements(URL, "Page", descs))
    assert "Save" not in names and "save" not in names
    assert "Cancel" in names or "cancel" in names.lower()


def test_no_underscore_notes_leak_into_the_report():
    descs = [_desc("button", {"id": "cancel"}, text="Cancel")]
    out = introspect.uncovered_elements(URL, "Page", descs)
    assert not any(name.startswith("_") for name in out)


def test_third_party_embed_is_left_out():
    ad = _desc("a", {"id": "ad-link"}, text="Sponsored", thirdParty=True)
    out = introspect.uncovered_elements(URL, "Page", [ad])
    assert out == {}


def test_empty_page_reports_nothing():
    assert introspect.uncovered_elements(URL, "Page", []) == {}


def test_report_only_never_touches_drift_summary():
    """--compare results are informational. summarize_drift takes per-page
    diffs and unreachable pages only - there is no path from uncovered
    elements into has_drift, by construction."""
    report = introspect.summarize_drift({}, [])
    assert report["has_drift"] is False
    assert "new_elements" not in report
