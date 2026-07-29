"""Unit tests for Phase-2 Tier-2 backlog 2.4 — update-mode step-def splicing.

Covers the pure helpers and the tiered orchestrator:

  _missing_feature_steps            — coverage diff (feature vs step-defs)
  _extract_new_step_functions       — pull decorated funcs from an LLM snippet
  _ensure_parsers_import            — import safety net
  _splice_step_defs_incremental     — Tier A (unchanged) / B (spliced) / C (fallback)

No Jira / LLM / network: the orchestrator is driven with a fake `gh` (returns
existing content), a fake `llm` (returns a canned snippet), and a monkeypatched
whole-regen fallback so every branch is exercised deterministically.
"""
import pytest

import agents.agent2_coder as coder
from agents.agent2_coder import (
    _missing_feature_steps,
    _extract_new_step_functions,
    _ensure_parsers_import,
    _splice_step_defs_incremental,
)

FEATURE = '''Feature: Login
  Scenario: valid login
    Given I am on the login page
    When I log in as "demo_user" with password "demo_pass"
    Then I see the products page
'''

FULLY_COVERED = '''import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from pages.some_page import SomePage

@given("I am on the login page")
def _(some_page):
    some_page.open()

@when(parsers.parse('I log in as "{u}" with password "{p}"'))
def _(some_page, u, p):
    some_page.login_as(u, p)

@then("I see the products page")
def _(inventory_page):
    assert inventory_page.is_loaded()
'''

MISSING_THEN = '''import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from pages.some_page import SomePage

@given("I am on the login page")
def _(some_page):
    some_page.open()

@when(parsers.parse('I log in as "{u}" with password "{p}"'))
def _(some_page, u, p):
    some_page.login_as(u, p)
'''


class FakeGH:
    def __init__(self, content=None, raise_exc=False):
        self.content = content
        self.raise_exc = raise_exc

    def get_file_content(self, path, branch="main"):
        if self.raise_exc:
            raise RuntimeError("not found on main")
        return self.content


class FakeLLM:
    def __init__(self, response=""):
        self.response = response
        self.calls = 0

    def invoke_text(self, system_prompt="", user_prompt=""):
        self.calls += 1
        return self.response


def _splice(gh, llm, step_defs_path="tests/step_defs/test_fake_splice.py"):
    return _splice_step_defs_incremental(
        llm, gh, "features/fake_splice.feature", FEATURE,
        step_defs_path, ctx=None, references={}, page_inventory="",
    )


# ─────────────────────────────────────────────────────────────
# _missing_feature_steps
# ─────────────────────────────────────────────────────────────

def test_missing_none_when_fully_covered():
    assert _missing_feature_steps(FEATURE, FULLY_COVERED) == []


def test_missing_reports_uncovered_then():
    assert _missing_feature_steps(FEATURE, MISSING_THEN) == [
        ("then", "I see the products page")
    ]


def test_missing_dedupes_repeated_steps():
    feat = (
        "Feature: F\n  Scenario: a\n    Given x\n"
        "  Scenario: b\n    Given x\n"
    )
    assert _missing_feature_steps(feat, "") == [("given", "x")]


# ─────────────────────────────────────────────────────────────
# _extract_new_step_functions
# ─────────────────────────────────────────────────────────────

def test_extract_single_function_from_fenced_snippet():
    snippet = (
        "```python\n"
        "from pytest_bdd import then\n"
        '@then("I see the products page")\n'
        "def _(inventory_page):\n"
        "    assert inventory_page.is_loaded()\n"
        "```"
    )
    funcs = _extract_new_step_functions(snippet)
    assert len(funcs) == 1
    assert "@then(" in funcs[0] and "def _(" in funcs[0]
    assert "import" not in funcs[0]


def test_extract_ignores_non_step_functions():
    snippet = (
        "def helper():\n    return 1\n\n"
        '@given("something")\n'
        "def _(page):\n    pass\n"
    )
    funcs = _extract_new_step_functions(snippet)
    assert len(funcs) == 1
    assert "@given(" in funcs[0]


def test_extract_returns_empty_on_unparseable():
    assert _extract_new_step_functions("def : broken(((") == []


def test_extract_returns_empty_when_no_step_funcs():
    assert _extract_new_step_functions("x = 1\ndef plain():\n    pass\n") == []


# ─────────────────────────────────────────────────────────────
# _ensure_parsers_import
# ─────────────────────────────────────────────────────────────

def test_ensure_parsers_import_inserts_after_last_import():
    content = "import pytest\nfrom pages.x import X\n\n@when(parsers.parse('a'))\ndef _(): pass\n"
    out = _ensure_parsers_import(content)
    assert "from pytest_bdd import parsers" in out
    # inserted right after the import block, before the decorator
    assert out.index("from pytest_bdd import parsers") < out.index("@when")


def test_ensure_parsers_import_noop_without_imports():
    content = "@when(parsers.parse('a'))\ndef _(): pass\n"
    assert _ensure_parsers_import(content) == content  # no anchor -> unchanged


# ─────────────────────────────────────────────────────────────
# _splice_step_defs_incremental — the tiers
# ─────────────────────────────────────────────────────────────

def test_tier_a_unchanged_makes_no_llm_call():
    gh = FakeGH(content=FULLY_COVERED)
    llm = FakeLLM(response="should never be called")
    content, mode = _splice(gh, llm)
    assert mode == "unchanged"
    assert content == FULLY_COVERED
    assert llm.calls == 0


def test_tier_b_splices_only_the_new_function():
    gh = FakeGH(content=MISSING_THEN)
    new_then = (
        '@then("I see the products page")\n'
        "def _(inventory_page):\n"
        "    assert inventory_page.is_loaded()\n"
    )
    llm = FakeLLM(response=new_then)
    content, mode = _splice(gh, llm)
    assert mode == "spliced"
    assert llm.calls == 1
    # existing functions preserved verbatim
    assert MISSING_THEN.rstrip() in content
    # new function appended and now covers the feature
    assert "I see the products page" in content
    assert _missing_feature_steps(FEATURE, content) == []


def test_tier_c_fallback_when_no_file_on_main(monkeypatch):
    monkeypatch.setattr(coder, "_regenerate_step_defs_whole",
                        lambda *a, **k: "WHOLE_REGEN")
    gh = FakeGH(raise_exc=True)
    llm = FakeLLM()
    content, mode = _splice(gh, llm)
    assert mode == "regenerated" and content == "WHOLE_REGEN"
    assert llm.calls == 0


def test_tier_c_fallback_when_existing_unusable(monkeypatch):
    monkeypatch.setattr(coder, "_regenerate_step_defs_whole",
                        lambda *a, **k: "WHOLE_REGEN")
    gh = FakeGH(content="   ")  # not useful python
    content, mode = _splice(gh, FakeLLM())
    assert mode == "regenerated" and content == "WHOLE_REGEN"


def test_tier_c_fallback_when_llm_returns_junk(monkeypatch):
    monkeypatch.setattr(coder, "_regenerate_step_defs_whole",
                        lambda *a, **k: "WHOLE_REGEN")
    gh = FakeGH(content=MISSING_THEN)
    llm = FakeLLM(response="no functions here, just prose")
    content, mode = _splice(gh, llm)
    assert mode == "regenerated" and content == "WHOLE_REGEN"


def test_tier_c_fallback_when_splice_still_uncovered(monkeypatch):
    monkeypatch.setattr(coder, "_regenerate_step_defs_whole",
                        lambda *a, **k: "WHOLE_REGEN")
    gh = FakeGH(content=MISSING_THEN)
    # LLM returns a step function, but for the WRONG phrase -> still uncovered.
    wrong = '@then("some other unrelated thing")\ndef _(page):\n    pass\n'
    content, mode = _splice(gh, FakeLLM(response=wrong))
    assert mode == "regenerated" and content == "WHOLE_REGEN"


def test_tier_c_fallback_on_duplicate_collision(monkeypatch):
    monkeypatch.setattr(coder, "_regenerate_step_defs_whole",
                        lambda *a, **k: "WHOLE_REGEN")
    # Force the duplicate guard to report a collision on the spliced result.
    monkeypatch.setattr(coder, "validate_no_duplicate_step_definitions",
                        lambda gfiles, root: ["Duplicate step-definition error in 'x': clash"])
    gh = FakeGH(content=MISSING_THEN)
    good = ('@then("I see the products page")\n'
            "def _(inventory_page):\n    assert inventory_page.is_loaded()\n")
    content, mode = _splice(gh, FakeLLM(response=good))
    assert mode == "regenerated" and content == "WHOLE_REGEN"