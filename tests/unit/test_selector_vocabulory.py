"""BasePage and the inventory sweep must understand the SAME selectors.

WHAT HAPPENED
    An inventory held a field written as `placeholder=<some hint text>`.
    verify_locators reported the page clean. Every test touching that field
    then failed in CI with:

        Locator.fill: Unknown engine "placeholder"

    `placeholder=`, `label=`, `alt=` and `title=` are not selector engines -
    they are get_by_* methods. inventory_tools/browser.py learned that on
    1 Aug 2026 and taught only itself; BasePage kept calling locator()
    directly.

    Two resolvers, one vocabulary. The tool whose whole job is catching bad
    selectors could not see this one, because it resolved the selector
    differently from the code that runs the test. Agents 1, 2 and 3 all passed;
    Agent 4 failed on something a sweep had already declared clean.

    These tests assert the two agree - not that either is individually
    correct, because either being right on its own is what produced the bug.
"""
import ast
import inspect
from pathlib import Path

import pytest

from pages.base_page import BasePage

# Every prefix that is a get_by_* method rather than a selector engine.
_GET_BY_PREFIXES = ("placeholder=", "label=", "alt=", "title=")


class _Scope:
    """Records which resolution method a selector was routed to."""

    def __init__(self):
        self.called = None

    def _record(self, name):
        def f(arg):
            self.called = (name, arg)
            return f"<{name}:{arg}>"
        return f

    def __getattr__(self, name):
        if name.startswith("get_by_") or name == "locator":
            return self._record(name)
        raise AttributeError(name)


@pytest.mark.parametrize("selector,expected", [
    ("placeholder=Some hint text", "get_by_placeholder"),
    ("label=Email Address", "get_by_label"),
    ("alt=Company logo", "get_by_alt_text"),
    ("title=Close", "get_by_title"),
])
def test_get_by_prefixes_are_not_passed_to_locator(selector, expected):
    """Routing these to locator() raises Unknown engine at RUN time - an error,
    not a miss, which reads as a broken test rather than a bad selector."""
    scope = _Scope()
    BasePage._resolve(scope, selector)
    method, arg = scope.called
    assert method == expected, f"{selector!r} went to {method}, not {expected}"
    assert "=" not in arg.split(" ", 1)[0] or arg == selector.split("=", 1)[1]
    assert arg == selector.split("=", 1)[1], "the prefix must be stripped"


@pytest.mark.parametrize("selector", [
    "#search_product",
    "input[placeholder='Some hint']",       # the css form is NOT a get_by_
    "text=Add to cart",
    "role=button[name='Sign in']",
    ".product-image-wrapper",
])
def test_real_engines_still_go_to_locator(selector):
    """css, text= and role= are native. Routing them anywhere else would break
    the majority of every inventory."""
    scope = _Scope()
    BasePage._resolve(scope, selector)
    assert scope.called[0] == "locator"


# Every selector shape an inventory is allowed to hold. Each must route the
# SAME WAY through both resolvers - that equivalence is the property, not any
# particular routing.
_VOCABULARY = [
    "placeholder=Some hint",
    "label=A field label",
    "alt=An image description",
    "title=A tooltip",
    "text=Some visible text",
    "role=button[name='An action']",
    "#an-id",
    ".a-class",
    "[data-test='a-hook']",
    "tag[attr='value']",
    "div.parent > a",
]


@pytest.mark.parametrize("selector", _VOCABULARY)
def test_both_resolvers_route_a_selector_identically(selector):
    """THE guard. Compares BEHAVIOUR, not source text.

    A textual check - "does this file mention placeholder=" - passes the moment
    someone writes the prefix in a comment, and fails to notice a resolver that
    mentions it but routes it somewhere else. The two must make the same call
    with the same argument, or an inventory written one way passes the sweep
    and fails the run.
    """
    from inventory_tools.browser import _resolve_one

    sweep_scope, runtime_scope = _Scope(), _Scope()
    _resolve_one(sweep_scope, selector)
    BasePage._resolve(runtime_scope, selector)

    assert sweep_scope.called == runtime_scope.called, (
        f"{selector!r} routes to {runtime_scope.called} at run time but "
        f"{sweep_scope.called} in the sweep. Whichever is wrong, they disagree "
        f"- so verify_locators cannot tell you whether a test will pass."
    )


def test_the_vocabulary_covers_what_the_crawler_emits():
    """A guard on the guard: the crawler must not invent a selector shape the
    list above has never been checked against."""
    from inventory_tools.introspect import rank_selector

    samples = [
        ("input", {"placeholder": "hint"}, ""),
        ("input", {"aria-label": "a label"}, ""),
        ("img", {"alt": "a picture"}, ""),
        ("a", {"title": "a tooltip"}, ""),
        ("button", {}, "An action"),
        ("a", {"href": "/somewhere"}, "A link"),
        ("div", {"id": "an-id"}, ""),
        ("div", {"data-test": "a-hook"}, ""),
    ]
    known_heads = {v.split("=", 1)[0] for v in _VOCABULARY if "=" in v}
    for tag, attrs, text in samples:
        selector, _ = rank_selector(tag, attrs, text)
        head, sep, _rest = selector.partition("=")
        if sep and head.isidentifier():
            assert head in known_heads, (
                f"the crawler emits {selector!r}, whose {head!r} prefix is not "
                f"in _VOCABULARY - so resolver parity was never checked for it"
            )


def test_no_committed_selector_uses_an_engine_the_runtime_rejects():
    """Applied to the real inventory: a selector BasePage cannot resolve is a
    guaranteed runtime failure, however clean the sweep reports it."""
    import json
    from core.app_context import AppContext

    inventory_path = AppContext.load().inventory_path()
    if not inventory_path.is_file():
        pytest.skip("no inventory configured yet")

    # An ENGINE prefix is a bare word before the first '=' AT THE START of the
    # selector. `a[href='/'] >> nth=0` is css with an index suffix, not an
    # engine called "a[href" - the first version of this check flagged every
    # pinned nav link, which would have had someone "fixing" correct selectors.
    known = ("text=", "role=", "id=", "data-testid=", "css=", "xpath=")
    data = json.loads(inventory_path.read_text(encoding="utf-8"))
    bad = []
    for page, entry in (data.get("pages") or {}).items():
        for key, selector in (entry.get("elements") or {}).items():
            if not isinstance(selector, str) or not selector:
                continue
            head, sep, _ = selector.partition("=")
            if not sep or not head.isidentifier():
                continue          # css, xpath, a bare id/class - no engine prefix
            if head + "=" not in known + _GET_BY_PREFIXES:
                bad.append(f"{page}.{key}: {selector}")
    assert not bad, (
        "selector(s) using an engine neither resolver knows:\n  " + "\n  ".join(bad))