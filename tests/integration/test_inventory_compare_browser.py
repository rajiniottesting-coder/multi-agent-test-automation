"""Live check for --compare (design E1): real Chromium, local HTML fixture.

Proves the browser side the pure tests cannot: a node an inventory selector
resolves to is marked and then excluded, an unmarked node is reported, and a
frame-prefixed selector marks the node inside its iframe.

Skipped - never failed - when Chromium cannot launch, so unit CI (which does not
install a browser) is unaffected. Run it locally with:
    playwright install chromium
    python -m pytest tests/integration/test_inventory_compare_browser.py -q
"""
import pytest

from inventory_tools import introspect
from inventory_tools.browser import browser_page, collect_uncovered

PAGE = """<!doctype html><html><head><title>Fixture</title></head><body>
<button id="save" data-qa="save-btn">Save</button>
<button id="cancel">Cancel</button>
<input type="email" name="email" placeholder="Email address">
<iframe id="frm" name="frm" src="child.html"></iframe>
</body></html>"""

CHILD = """<!doctype html><html><body>
<button id="child-btn">Child action</button>
<input type="text" name="childbox">
</body></html>"""


@pytest.fixture
def fixture_url(tmp_path):
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    (tmp_path / "child.html").write_text(CHILD, encoding="utf-8")
    return (tmp_path / "index.html").as_uri()


@pytest.fixture
def page():
    try:
        with browser_page() as p:
            yield p
    except Exception as exc:                       # no Chromium on this machine
        pytest.skip(f"Chromium unavailable: {exc}")


def _ids(descriptors):
    return {d["attrs"].get("id") or d["attrs"].get("name") for d in descriptors}


def test_marked_nodes_are_covered_and_the_rest_are_reported(page, fixture_url):
    selectors = ["[data-qa='save-btn']", "iframe#frm >>> #child-btn"]
    title, descs = collect_uncovered(page, fixture_url, selectors)
    assert title == "Fixture"

    uncovered = introspect.uncovered_descriptors(descs)
    left = _ids(uncovered)
    assert "save" not in left and "child-btn" not in left
    assert {"cancel", "email", "childbox"} <= left


def test_uncovered_report_uses_frame_prefixed_selectors_for_child_frames(page, fixture_url):
    title, descs = collect_uncovered(page, fixture_url, ["[data-qa='save-btn']"])
    out = introspect.uncovered_elements(fixture_url, title, descs)
    assert any(sel.startswith("iframe#frm") and "childbox" in sel
               for sel in out.values()), out


def test_marking_does_not_change_what_the_page_shows(page, fixture_url):
    _, before = collect_uncovered(page, fixture_url, [])
    _, after = collect_uncovered(page, fixture_url, ["[data-qa='save-btn']"])
    assert len(before) == len(after)
