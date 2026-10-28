"""The nightly inventory check says what it found, about every page.

Found when the pipeline health issue reported Inventory Health failing three
nights in a row (25-27 Oct 2026):

  - The report said `AMBIG(2) <key> text=<heading text>` and no more: which
    two elements matched could only be learned by reproducing the run
    locally. An unexpected multi-match now lists each match - tag, id,
    classes, shown or hidden, text - so the nightly report alone is enough to
    choose the element meant. (Run in real Chromium while this was built: the
    `text=` selector also caught a link reading "all products" and a hidden
    element - Playwright's `text=` is a case-insensitive substring match.)
  - The verifier signed in first and then visited every page, so the login
    page - which a signed-in browser is sent away from - "did not render" every
    night and its selectors were never checked. It is now verified signed out,
    before signing in, and not again after.
  - inventory_tools/browser.py held a JavaScript regex (`\\s`) in a plain
    Python string: a SyntaxWarning on every run, an error in later Python
    versions. No source file may carry an invalid escape now.

Generic: no application, page or selector of the deployment is named here.
"""
import ast
import warnings
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _locator(count, described=()):
    return SimpleNamespace(count=lambda: count,
                           evaluate_all=lambda js, limit: list(described)[:limit],
                           nth=lambda i: MagicMock(bounding_box=lambda: None))


@pytest.fixture
def vl(monkeypatch):
    from scripts import verify_locators as mod
    monkeypatch.setattr(mod, "_wait_for_render", lambda page, sels, *a, **k: True)
    monkeypatch.setattr(mod, "_highlight", lambda *a, **k: False)
    return mod


def test_an_ambiguous_selector_lists_what_it_matched(vl, monkeypatch, capsys):
    matches = ['<h2.title> shown "Heading"', '<a#menu.nav> shown "heading"']
    monkeypatch.setattr(vl, "_resolve_one", lambda page, sel: _locator(
        2 if sel == "text=Heading" else 1, matches if sel == "text=Heading" else ()))
    entry = {"url": "/p", "elements": {"heading": "text=Heading", "save": "#save"}}
    assert vl._verify_page(MagicMock(), "https://x.test", "p", entry, 0, False) == (1, 1)
    out = capsys.readouterr().out
    assert "AMBIG(2)" in out
    assert '1. <h2.title> shown "Heading"' in out and '2. <a#menu.nav> shown "heading"' in out


def test_more_matches_than_described_are_counted(vl, monkeypatch, capsys):
    lines = [f'<li.row> shown "{i}"' for i in range(5)]
    monkeypatch.setattr(vl, "_resolve_one", lambda page, sel: _locator(9, lines))
    vl._verify_page(MagicMock(), "https://x.test", "p", {"url": "/p", "elements": {"r": "li"}},
                    0, False)
    out = capsys.readouterr().out
    assert "5. <li.row>" in out and "... and 4 more" in out


def test_a_declared_family_is_not_described(vl, monkeypatch, capsys):
    monkeypatch.setattr(vl, "_resolve_one", lambda page, sel: _locator(3, ["<li> shown"] * 3))
    entry = {"url": "/p", "multi_match": ["rows"], "elements": {"rows": "li.row"}}
    assert vl._verify_page(MagicMock(), "https://x.test", "p", entry, 0, False) == (1, 0)
    assert "1. <li>" not in capsys.readouterr().out


def test_a_description_that_cannot_be_read_never_fails_the_check(vl, monkeypatch, capsys):
    def broken(js, limit):
        raise RuntimeError("detached")
    monkeypatch.setattr(vl, "_resolve_one", lambda page, sel: SimpleNamespace(
        count=lambda: 2, evaluate_all=broken))
    assert vl._verify_page(MagicMock(), "https://x.test", "p",
                           {"url": "/p", "elements": {"h": "h2"}}, 0, False) == (0, 1)
    assert "AMBIG(2)" in capsys.readouterr().out


def test_the_description_script_is_valid_and_bounded():
    from scripts import verify_locators as vl
    js = vl._DESCRIBE_JS
    assert js.strip().startswith("(els, limit) =>") and "els.slice(0, limit)" in js
    assert "/\\s+/" in js and "/\\\\s+/" not in js, "the regex reaches the page as written"
    assert vl._MAX_DESCRIBED == 5


# ── the login page, signed out ──────────────────────────────────────────────

INVENTORY = {"pages": {
    "home": {"url": "/", "elements": {"logo": "#logo"}},
    "signin": {"url": "/account/login/", "elements": {"user": "#user", "pass": "#pass"}},
    "cart": {"url": "/cart", "elements": {"rows": "tr"}},
}}


def test_the_pages_served_at_the_login_path():
    from scripts.verify_locators import signed_out_pages
    assert list(signed_out_pages(INVENTORY, "/account/login")) == ["signin"]
    assert list(signed_out_pages(INVENTORY, "/account/login?next=/cart")) == ["signin"]
    assert signed_out_pages(INVENTORY, "/account/login", only_page="cart") == {}
    assert signed_out_pages(INVENTORY, None) == {}
    assert signed_out_pages({}, "/x") == {}


def _run_main(monkeypatch, tmp_path, argv, found_login="/account/login/"):
    import json
    import sys
    from scripts import verify_locators as vl
    inv = tmp_path / "inv.json"
    inv.write_text(json.dumps(INVENTORY))
    events = []
    monkeypatch.setattr(vl.AppContext, "load", staticmethod(lambda: SimpleNamespace(
        base_url="https://x.test", inventory_path=lambda: inv)))

    @contextmanager
    def browser(headless=True):
        yield MagicMock(url="https://x.test/")
    monkeypatch.setattr(vl, "browser_page", browser)
    monkeypatch.setattr(vl, "find_login_path", lambda inventory: found_login)
    monkeypatch.setattr(vl, "do_login", lambda *a, **k: events.append("login") or True)

    def verify(page, base_url, name, entry, pause, only_problems, state=""):
        events.append(f"{name}{'(' + state + ')' if state else ''}")
        return (len(entry["elements"]), 0)
    monkeypatch.setattr(vl, "_verify_page", verify)
    monkeypatch.setattr(sys, "argv", ["verify_locators", "--headless", "--username", "u",
                                      "--password", "p", *argv])
    return vl.main(), events


def test_the_login_page_is_verified_signed_out_before_signing_in(monkeypatch, tmp_path, capsys):
    code, events = _run_main(monkeypatch, tmp_path, [])
    assert events == ["signin(signed out)", "login", "home", "cart"], \
        "verified once, before signing in - never after, when it cannot render"
    assert code == 0
    assert "4 selector(s) resolve to exactly one element" in capsys.readouterr().out, \
        "1 (home) + 2 (signin, signed out) + 1 (cart): the signed-out page counted once"


def test_an_explicit_login_url_is_honoured(monkeypatch, tmp_path):
    _code, events = _run_main(monkeypatch, tmp_path, ["--login-url", "/account/login"],
                              found_login=None)
    assert events[:2] == ["signin(signed out)", "login"]


def test_a_guessed_root_is_not_treated_as_a_login_page(monkeypatch, tmp_path):
    """No login page in the inventory: the root is only a fallback guess - the
    home page is checked signed in, as before."""
    _code, events = _run_main(monkeypatch, tmp_path, [], found_login=None)
    assert events == ["login", "home", "signin", "cart"]


def test_one_page_asked_for_is_checked_in_its_own_state(monkeypatch, tmp_path):
    _code, events = _run_main(monkeypatch, tmp_path, ["--page", "signin"])
    assert events == ["signin(signed out)", "login"]
    _code, events = _run_main(monkeypatch, tmp_path, ["--page", "cart"])
    assert events == ["login", "cart"]


def test_without_signing_in_nothing_moves(monkeypatch, tmp_path):
    _code, events = _run_main(monkeypatch, tmp_path, ["--no-login"])
    assert events == ["home", "signin", "cart"]


# ── no invalid escape in any source file ────────────────────────────────────

_SOURCES = sorted(p for d in ("agents", "core", "integrations", "inventory_tools", "pages",
                              "scripts", "validators", "config", "tests")
                  for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)


def test_no_source_file_has_an_invalid_escape():
    """A regex or path in a plain string ("\\s", "\\d") is a SyntaxWarning
    today and a SyntaxError in later Python versions."""
    offenders = []
    for path in _SOURCES:
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            try:
                ast.parse(path.read_text(encoding="utf-8"), str(path))
            except SyntaxError as e:
                offenders.append(f"{path.relative_to(ROOT)}:{e.lineno}: {e.msg}")
    assert len(_SOURCES) > 100
    assert not offenders, "use a raw string (r\"...\") or escape the backslash:\n" + \
        "\n".join(offenders)


# ── a contains-match text selector: the fix, and the ones to tighten ───────
#
# Found on the second drift report (run #90, 28 Oct 2026): the site added a
# visible "<words> Catalog" span, and an unquoted `text=<words>` heading
# selector - a case-insensitive substring match - caught it too. The report's
# advice was to declare the heading a multi_match family, which would have
# hidden the drift. Proven in real Chromium while this was built: the quoted
# form matched only the heading, extra whitespace included.

@pytest.mark.parametrize("selector, exact", [
    ("text=Some Words", 'text="Some Words"'),
    ("text= Some Words ", 'text="Some Words"'),
    ('text=Say "hi"', 'text="Say \\"hi\\""'),
    ('text="Some Words"', None),
    ("text='Some Words'", None),
    ("css=div >> text=Some Words", None),
    ("#an-id", None),
    ("role=heading[name='Some Words']", None),
])
def test_the_exact_form_of_a_text_selector(selector, exact):
    from scripts.verify_locators import exact_text_form
    assert exact_text_form(selector) == exact


def _counts(mapping):
    return lambda page, sel: _locator(mapping[sel], ['<span> shown "Some Words Catalog"',
                                                     '<h2.title> shown "Some Words"'])


def test_an_ambiguous_text_selector_is_given_its_exact_fix(vl, monkeypatch, capsys):
    monkeypatch.setattr(vl, "_resolve_one", _counts({"text=Some Words": 2,
                                                     'text="Some Words"': 1}))
    entry = {"url": "/p", "elements": {"heading": "text=Some Words"}}
    assert vl._verify_page(MagicMock(), "https://x.test", "p", entry, 0, False) == (0, 1), \
        "still a failure until the inventory is fixed"
    out = capsys.readouterr().out
    assert 'fix: text="Some Words" matches exactly one' in out
    assert '"multi_match"' not in out, "never told to declare a heading a family"


def test_without_an_exact_fix_the_family_advice_says_when_it_applies(vl, monkeypatch, capsys):
    monkeypatch.setattr(vl, "_resolve_one", _counts({"li.row": 3}))
    vl._verify_page(MagicMock(), "https://x.test", "p", {"url": "/p", "elements": {"rows": "li.row"}},
                    0, False)
    out = capsys.readouterr().out
    assert "Meant to be ONE element? Tighten its selector" in out
    assert "never declare it a family to silence it" in out
    assert '"multi_match": ["rows"]' in out


def test_a_text_selector_that_could_be_exact_is_listed_not_failed(vl, monkeypatch, capsys):
    monkeypatch.setattr(vl, "_resolve_one", _counts({
        "text=Heading": 1, 'text="Heading"': 1,          # can be tightened
        "text=Greeting": 1, 'text="Greeting"': 0,        # its element says more: keep
        "#save": 1}))
    entry = {"url": "/p", "elements": {"heading": "text=Heading", "greeting": "text=Greeting",
                                       "save": "#save"}}
    assert vl._verify_page(MagicMock(), "https://x.test", "p", entry, 0, False) == (3, 0)
    out = capsys.readouterr().out
    assert "note: 1 key(s) on [p] resolve today through a contains-match" in out
    assert 'heading                      text="Heading"' in out
    assert "greeting" not in out.split("note:")[1]


def test_declared_families_and_conditional_keys_are_never_tightened(vl, monkeypatch, capsys):
    monkeypatch.setattr(vl, "_resolve_one", _counts({"text=Add": 4, 'text="Add"': 1,
                                                     "text=Saved": 0, 'text="Saved"': 0}))
    entry = {"url": "/p", "multi_match": ["adds"], "conditional": ["saved"],
             "elements": {"adds": "text=Add", "saved": "text=Saved"}}
    vl._verify_page(MagicMock(), "https://x.test", "p", entry, 0, False)
    out = capsys.readouterr().out
    assert "fix:" not in out and "note:" not in out.replace("note: declared multi_match", "")
