"""Every BasePage action waits for the page to finish loading first.

Found from a trace of a run that failed three cart scenarios at once (28 Oct
2026): a page reached by a CLICK showed its heading at +11.5 s, the test
clicked the page's add button at +11.5 s, and the script that handles that
button finished downloading at +19.1 s. The click went to a button nothing was
listening to - no request, no confirmation - and the failure read as a state
problem. navigate() never had this gap (page.goto waits for the load event);
a click-navigation did. Now every action waits for the load event first
(BasePage._wait_for_page_scripts), bounded and fail-open.

Also: a wait for a row, a family or a hidden element that fails now carries
the page's action requests, as wait_visible's failure already did - the
remove in that run failed with a bare call log and was triaged "unclassified".
"""
import ast
import http.server
import logging
import os
import socketserver
import textwrap
import threading
import time
from pathlib import Path

import pytest

import pages.base_page as bp
from pages.base_page import BasePage

ROOT = Path(__file__).resolve().parents[2]


# ── the wait itself, on a fake page ──────────────────────────────────────────

class _Page:
    def __init__(self, states, url="https://app.example/detail", load_raises=False):
        self.states = list(states)
        self.url = url
        self.load_raises = load_raises
        self.loads = []

    def evaluate(self, expression):
        assert expression == "document.readyState"
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if isinstance(state, Exception):
            raise state
        return state

    def wait_for_load_state(self, state, timeout=None):
        self.loads.append((state, timeout))
        if self.load_raises:
            raise TimeoutError("Timeout exceeded while waiting for event \"load\"")


def test_a_loaded_document_costs_one_check_and_no_wait():
    page = _Page(["complete"])
    BasePage(page)._wait_for_page_scripts()
    assert page.loads == []


@pytest.mark.parametrize("state", ["loading", "interactive"])
def test_a_document_still_loading_is_waited_for(state):
    page = _Page([state])
    BasePage(page)._wait_for_page_scripts()
    assert page.loads == [("load", BasePage._default_timeout_ms())]


def test_a_page_mid_navigation_is_left_to_the_actions_own_wait():
    page = _Page([RuntimeError("Execution context was destroyed")])
    BasePage(page)._wait_for_page_scripts()
    assert page.loads == []


def test_a_page_that_never_loads_costs_one_timeout_then_is_acted_on(caplog):
    page = _Page(["loading"], load_raises=True)
    obj = BasePage(page)
    with caplog.at_level(logging.WARNING, logger="pages.base_page"):
        obj._wait_for_page_scripts()                   # waits, gives up, never raises
        obj._wait_for_page_scripts()                   # same document: no second wait
    assert len(page.loads) == 1
    assert "had not finished loading" in caplog.text and page.url in caplog.text
    page.url = "https://app.example/next"              # another document: waits again
    obj._wait_for_page_scripts()
    assert len(page.loads) == 2


def test_the_memo_is_per_page_not_global():
    a, b = _Page(["loading"], load_raises=True), _Page(["loading"], load_raises=True)
    BasePage(a)._wait_for_page_scripts()
    BasePage(b)._wait_for_page_scripts()
    assert len(a.loads) == 1 and len(b.loads) == 1


def test_a_fake_page_without_evaluate_is_left_alone():
    """Other tests drive BasePage with minimal fakes: the wait must never break them."""
    class Bare:
        url = "x"
    BasePage(Bare())._wait_for_page_scripts()
    BasePage.__new__(BasePage)._wait_for_page_scripts()   # built without a page at all


# ── every action goes through it ────────────────────────────────────────────

_ACTIONS = {"click", "dblclick", "fill", "press", "press_sequentially", "type",
            "check", "uncheck", "set_checked", "select_option", "hover", "tap",
            "drag_to", "set_input_files", "down", "up", "move", "dispatch_event"}

# Driving the browser on purpose without waiting for the page: clearing an ad
# interstitial must work on a page that is still loading behind it.
_EXEMPT = {"dismiss_interstitial"}


def _base_page_functions():
    tree = ast.parse((ROOT / "pages" / "base_page.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BasePage")
    return [n for n in cls.body if isinstance(n, ast.FunctionDef)]


def _is_browser_action(call: ast.Call) -> bool:
    """`<locator or page>.click(...)` - not `self.click(...)`, which is a
    BasePage helper and waits by itself."""
    f = call.func
    return (isinstance(f, ast.Attribute) and f.attr in _ACTIONS
            and not (isinstance(f.value, ast.Name) and f.value.id == "self"))


def _first_wait_line(fn):
    lines = [c.lineno for c in ast.walk(fn) if isinstance(c, ast.Call)
             and isinstance(c.func, ast.Attribute) and c.func.attr == "_wait_for_page_scripts"]
    return min(lines) if lines else None


def test_every_action_helper_waits_for_the_page_before_driving_it():
    missing = []
    for fn in _base_page_functions():
        if fn.name in _EXEMPT or fn.name == "_wait_for_page_scripts":
            continue
        actions = [c.lineno for c in ast.walk(fn)
                   if isinstance(c, ast.Call) and _is_browser_action(c)]
        if not actions:
            continue
        wait = _first_wait_line(fn)
        if wait is None or wait > min(actions):
            missing.append(f"{fn.name} (line {min(actions)})")
    assert not missing, ("these BasePage helpers drive the browser without "
                         "self._wait_for_page_scripts() first: " + ", ".join(missing))


def test_the_guard_would_catch_a_new_helper():
    fn = ast.parse(textwrap.dedent('''
        def tap_it(self, locator):
            self._locator(locator).tap()
    ''')).body[0]
    assert [c for c in ast.walk(fn) if isinstance(c, ast.Call) and _is_browser_action(c)]
    assert _first_wait_line(fn) is None
    helper = ast.parse("def f(self, x):\n    self.click(x)\n").body[0]
    assert not [c for c in ast.walk(helper) if isinstance(c, ast.Call) and _is_browser_action(c)]


def test_the_guard_covers_the_helpers_the_trace_failed_in():
    names = {fn.name for fn in _base_page_functions() if _first_wait_line(fn)}
    assert {"click", "click_in_row", "click_nth", "fill"} <= names


# ── a failed row / family / hidden wait says what the page requested ────────

class _Locator:
    def filter(self, **kw):
        return self


@pytest.fixture
def watched(monkeypatch):
    class P:
        url = "https://app.example/cart"
        def on(self, *a):
            pass
    page = P()
    bp.watch_network(page)
    bp._NETWORK_LOG[page].append(("GET https://app.example/cart - HTTP 200", False))
    obj = BasePage(page)
    monkeypatch.setattr(obj, "_locator", lambda sel: _Locator())
    return obj


def _expect_failing(message):
    class E:
        def __getattr__(self, name):
            def fail(*a, **k):
                raise AssertionError(message)
            return fail
    return lambda target: E()


@pytest.mark.parametrize("call", [
    lambda o: o.wait_for_row("tr", "Item", present=False, timeout_ms=1),
    lambda o: o.wait_for_row("tr", "Item", present=True, timeout_ms=1),
    lambda o: o.wait_for_any("li", present=False, timeout_ms=1),
    lambda o: o.wait_hidden("#dialog", timeout_ms=1),
])
def test_a_failed_wait_carries_the_pages_action_requests(watched, monkeypatch, call):
    original = "Locator expected to have count '0'\nActual value: 1"
    monkeypatch.setattr(bp, "expect", _expect_failing(original))
    with pytest.raises(AssertionError) as info:
        call(watched)
    text = str(info.value)
    assert text.startswith(original), "Playwright's own message stays first, unchanged"
    assert "GET https://app.example/cart - HTTP 200" in text
    assert "never reached the application" in text


def test_an_unwatched_page_fails_exactly_as_before(monkeypatch):
    class P:
        url = "u"
    obj = BasePage(P())
    monkeypatch.setattr(obj, "_locator", lambda sel: _Locator())
    monkeypatch.setattr(bp, "expect", _expect_failing("plain message"))
    with pytest.raises(AssertionError) as info:
        obj.wait_for_row("tr", "Item", present=False, timeout_ms=1)
    assert str(info.value) == "plain message"


# ── in a real browser: the race the trace showed, and the fix ───────────────

_DELAY_S = 1.5


class _Handler(http.server.BaseHTTPRequestHandler):
    added = 0

    def log_message(self, *a):
        pass

    def _send(self, body, kind="text/html"):
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/start":
            self._send('<a id="go" href="/detail">open</a>')
        elif self.path == "/detail":
            self._send('<h1 id="title">Detail</h1><button id="add">Add</button>'
                       '<div id="done" hidden>added</div><script src="/slow.js"></script>')
        elif self.path == "/slow.js":
            time.sleep(_DELAY_S)                       # the script arrives late
            self._send("document.getElementById('add').onclick = () => "
                       "fetch('/add').then(() => { document.getElementById('done')"
                       ".hidden = false; });", "application/javascript")
        elif self.path == "/add":
            type(self).added += 1
            self._send("ok", "text/plain")
        else:
            self.send_error(404)


@pytest.fixture(scope="module")
def server():
    class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    srv = S(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    sync = pytest.importorskip("playwright.sync_api")
    pw = sync.sync_playwright().start()
    try:
        exe = os.environ.get("CHROMIUM_EXECUTABLE")
        b = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
    except Exception as exc:                           # noqa: BLE001
        pw.stop()
        pytest.skip(f"no browser to launch here: {type(exc).__name__}")
    yield b
    b.close()
    pw.stop()


def _open_detail_by_click(browser, server):
    page = browser.new_page()
    page.goto(f"{server}/start")
    obj = BasePage(page)
    obj.click("#go")                                   # a click-navigation, like the trace
    obj.wait_visible("#title")                         # the heading is up long before the script
    return page, obj


def test_in_a_browser_the_race_is_real(browser, server, monkeypatch):
    """Without the wait, the click goes to a button nothing is listening to."""
    monkeypatch.setattr(BasePage, "_wait_for_page_scripts", lambda self: None)
    _Handler.added = 0
    page, obj = _open_detail_by_click(browser, server)
    obj.click("#add")
    page.wait_for_load_state("load")
    assert _Handler.added == 0 and page.locator("#done").is_hidden()
    page.close()


def test_in_a_browser_the_action_now_reaches_the_application(browser, server):
    _Handler.added = 0
    page, obj = _open_detail_by_click(browser, server)
    obj.click("#add")
    obj.wait_visible("#done", timeout_ms=5000)
    assert _Handler.added == 1
    page.close()
