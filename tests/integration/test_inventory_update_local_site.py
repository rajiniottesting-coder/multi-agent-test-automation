"""P1-4 end to end with a REAL browser against a local site (opt-in).

    INVENTORY_E2E=1 pytest tests/integration/ -o addopts=""
    # a Chromium other than Playwright's default: PLAYWRIGHT_CHROMIUM_EXECUTABLE=<path>

Runs the real crawl (scripts.check_inventory_staleness --compare), the real
nightly update (core.inventory_update) and verify_locators against a small
generic site served on 127.0.0.1, in three phases:

  1   before deployment - a planned element absent, a planned page answering 404
  1b  a placeholder answering at the planned page's url (a soft 404)
  2   after deployment - both live

The footer (an email field and a button) is on every page and in the inventory
once, under `home`: the shape of PR #228. A menu link no key covers is on every
page too: the shape the first real run of this change found still being added
once per page. Not in CI (Agent 4 runs tests/unit and tests/step_defs): it
needs a browser and takes about a minute. Generic pages only.
"""
import contextlib
import http.server
import io
import json
import os
import socketserver
import sys
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(os.getenv("INVENTORY_E2E") != "1",
                                reason="opt-in: set INVENTORY_E2E=1 (needs a browser)")

STATE = {"phase": 1}
FOOTER = ('<footer><h2>Subscription</h2><input type="email" placeholder="Your email address">'
          '<button id="subscribe" aria-label="Subscribe">&#8594;</button></footer>')
NAV = ('<nav><a href="/">Home</a> <a href="/list">Items</a> <a href="/about">About</a> '
       '<a href="/news/a">News A</a> <a href="/news/b">News B</a> <a href="/logo.png">Logo</a> '
       '<a href="https://external.example/x">Partner</a> <a href="mailto:a@b.example">Mail</a>'
       ' <a href="/item/2">Item 2</a> <a href="/wish">Wish</a></nav>')


def _page(body, title):
    return (f"<!doctype html><html><head><title>{title}</title></head>"
            f"<body>{NAV}<main>{body}</main>{FOOTER}</body></html>")


def _route(path):
    phase = STATE["phase"]
    if path == "/":
        return 200, _page("<h1>Welcome</h1><button>Shop now</button>", "Home")
    if path == "/list":
        coupon = '<input data-test="coupon" placeholder="Coupon code">' if phase == 2 else ""
        return 200, _page('<h1>All items</h1><table><tr class="row"><td>A</td></tr>'
                          '<tr class="row"><td>B</td></tr></table>'
                          f"<button>Sort by price</button>{coupon}", "Items")
    if path.startswith("/item/"):
        return 200, _page('<h1>Item</h1><button>Add to basket</button>'
                          '<form id="review-form"><textarea placeholder="Your review"></textarea>'
                          "<button>Send review</button></form>", "Item")
    if path == "/wish":
        if phase == 1:
            return 404, "<html><body>Not found</body></html>"
        if phase == 15:
            return 200, _page("<h1>Coming soon</h1><button>Notify me</button>", "Soon")
        return 200, _page("<h1>Wish list</h1><button>Clear all</button>", "Wish")
    return 404, "<html><body>Not found</body></html>"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        code, html = _route(self.path.split("?")[0])
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, *a):
        pass


INVENTORY = {"app_name": "Local", "pages": {
    "nav": {"url": "/", "always": True, "components": ["Nav"],
            "elements": {"home_link": "role=link[name='Home']",
                         "items_link": "role=link[name='Items']"}},
    "home": {"url": "/", "components": ["Home"],
             "elements": {"subscribe_email_input": "placeholder=Your email address",
                          "subscribe_button": "#subscribe",
                          "shop_now_button": "role=button[name='Shop now']"}},
    "list": {"url": "/list", "components": ["Items"], "multi_match": ["rows"],
             "planned": ["coupon_input"],
             "elements": {"heading": "text=All items", "rows": ".row",
                          "coupon_input": "[data-test='coupon']"}},
    "item": {"url": "/item/{id}", "url_sample": "/item/1", "components": ["Items"],
             "elements": {"add_button": "role=button[name='Add to basket']"}},
    "wish": {"url": "/wish", "components": ["Wish"], "planned_page": True,
             "planned": ["heading"], "elements": {"heading": "role=heading[name='Wish list']"}},
}}


@contextmanager
def _browser():
    from playwright.sync_api import sync_playwright
    exe = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, executable_path=exe)
        ctx = b.new_context()
        ctx.set_default_timeout(15000)
        try:
            yield ctx.new_page()
        finally:
            ctx.close()
            b.close()


@pytest.fixture(scope="module")
def site():
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture(scope="module")
def phases(site, tmp_path_factory):
    from core import inventory_update as iu
    from scripts import check_inventory_staleness as chk
    work = tmp_path_factory.mktemp("e2e")
    inv_path = work / "inv.json"
    inv_path.write_text(json.dumps(INVENTORY, indent=2) + "\n")
    saved = (chk.browser_page, chk.AppContext.load, sys.argv)
    chk.browser_page = lambda headless=True, timeout_ms=15000: _browser()
    chk.AppContext.load = staticmethod(lambda: SimpleNamespace(
        name="Local", base_url=site, inventory_path=lambda: inv_path,
        inventory_file=str(inv_path)))
    out = {}
    try:
        for phase in (1, 15, 2):
            STATE["phase"] = phase
            report_path = work / f"drift_{phase}.json"
            sys.argv = ["chk", "--no-login", "--compare", "--json", str(report_path)]
            with contextlib.redirect_stdout(io.StringIO()):
                code = chk.main()
            report = json.loads(report_path.read_text())
            upd = iu.build_update(report, json.loads(inv_path.read_text()), set())
            out[phase] = SimpleNamespace(code=code, report=report, upd=upd,
                                         body=iu.render_body(upd, "inv.json", "d"))
    finally:
        chk.browser_page, chk.AppContext.load, sys.argv = saved
    return out


@pytest.mark.parametrize("phase", [1, 15, 2])
def test_shared_sections_are_listed_never_added(phases, phase):
    r = phases[phase]
    added = {(a["page"], a["element"]) for a in r.upd.added}
    assert not any(e in ("email_address_input", "subscribe_button") for _p, e in added)
    assert {(s["page"], s["covered_by"]) for s in r.upd.shared} >= {
        ("list", "home.subscribe_email_input"), ("item", "home.subscribe_button")}
    assert ("home", "mail_link") not in added
    assert [l["element"] for l in r.upd.layout].count("mail_link") == 1
    assert {("list", "sort_by_price_button"), ("item", "send_review_button")} <= added
    assert r.code == 0 and r.report["has_drift"] is False and r.upd.removed == []
    assert [(u["group"], u["count"]) for u in r.upd.unlisted_paths] == [("/news", 2), ("/about", 1)]


def test_before_deployment_planned_entries_wait(phases):
    r = phases[1]
    assert r.report["unreachable_pages"] == [] and r.upd.planned_pages_waiting == ["wish"]
    assert [w["element"] for w in r.upd.planned_waiting] == ["coupon_input"]
    assert r.report["pages"]["list"]["missing"] == []


def test_a_placeholder_at_a_planned_url_is_not_the_page(phases):
    r = phases[15]
    assert r.upd.planned_pages_waiting == ["wish"]
    assert not any(a["page"] == "wish" for a in r.upd.added)


def test_after_deployment_planned_entries_are_confirmed_and_crawled(phases):
    r = phases[2]
    confirmed = {(x["page"], x["element"], x["page_confirmed"]) for x in r.upd.confirmed}
    assert {("list", "coupon_input", False), ("wish", "heading", True)} <= confirmed
    assert {"page": "wish", "element": "clear_all_button",
            "selector": "role=button[name='Clear all']"} in r.upd.added
    pages = r.upd.inventory["pages"]
    assert "planned" not in pages["list"] and "planned" not in pages["wish"]
    assert "planned_page" not in pages["wish"]
    for title in ("Planned elements now live - confirmed",
                  "Not added - already covered on another page",
                  "Not added - new on every page: a shared section", "page confirmed live"):
        assert title in r.body


@pytest.mark.parametrize("phase, name, verdict", [
    (1, "list", "PLAN "), (1, "wish", "PLANNED PAGE"), (2, "list", "LIVE "), (2, "wish", "LIVE ")])
def test_verify_locators_on_the_real_pages(site, phase, name, verdict):
    from scripts import verify_locators as vl
    STATE["phase"] = phase
    with _browser() as page:
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            _good, bad = vl._verify_page(page, site, name, INVENTORY["pages"][name], 0, False)
    assert verdict in printed.getvalue() and bad == 0
