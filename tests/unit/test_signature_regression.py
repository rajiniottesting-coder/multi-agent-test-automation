"""A regenerated page object must not change a signature committed tests rely on.

THE CASE THIS CATCHES
    Twenty tests are on main. A new story regenerates a shared page object and
    keeps `look_up`, but as `look_up(self, term, category)`. The
    story's own step definitions are written against the new signature, so
    every check on the batch passes. Every committed test still calls
    `look_up(term)` and raises TypeError when Agent 4 runs it.

    The dropped-method check (test_committed_tree_resolves.py) asks whether a
    method still EXISTS. This asks whether the call still FITS - and reports
    only what the batch broke, so an old defect never blocks a new story.

Every test builds its own project in a temporary folder, so none depends on
what happens to be committed and none can skip.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from validators.method_resolution_validator import (
    _bindable_signatures,
    _call_binds,
    _signatures_broken_by_regeneration,
    validate_method_resolution,
)

_PAGE = "pages/example_page.py"
_OLD_PAGE = '''from pages.base_page import BasePage


class ExamplePage(BasePage):
    def look_up(self, term: str) -> None:
        self.fill(self.sel("key_a"), term)

    def listed_values(self) -> list:
        return []
'''
_CALLER = '''from pytest_bdd import when


@when("the user looks something up")
def look_up_step(example_page):
    example_page.look_up("value-one")
'''


def _project(tmp_path: Path, caller: str = _CALLER, page: str = _OLD_PAGE) -> Path:
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "base_page.py").write_text(
        "class BasePage:\n    pass\n", encoding="utf-8")
    (tmp_path / _PAGE).write_text(page, encoding="utf-8")
    (tmp_path / "tests" / "step_defs").mkdir(parents=True)
    (tmp_path / "tests" / "step_defs" / "test_old_lookup.py").write_text(
        caller, encoding="utf-8")
    return tmp_path


def _regenerated(new_signature: str, body: str = "        pass\n") -> list:
    content = _OLD_PAGE.replace(
        "    def look_up(self, term: str) -> None:\n"
        "        self.fill(self.sel(\"key_a\"), term)\n",
        f"    def look_up({new_signature}) -> None:\n{body}")
    assert content != _OLD_PAGE
    return [SimpleNamespace(file_path=_PAGE, content=content, is_new_file=False)]


# ── what must be rejected ────────────────────────────────────────────────────

def test_a_new_required_parameter_breaks_the_committed_caller(tmp_path):
    errors = _signatures_broken_by_regeneration(
        _regenerated("self, term: str, category: str"), _project(tmp_path))
    assert len(errors) == 1
    err = errors[0]
    assert err.startswith(f"Call signature error in '{_PAGE}'"), \
        "must name the page object, so the repair loop regenerates that file"
    assert "tests/step_defs/test_old_lookup.py line 6" in err
    assert "(term)" in err and "(term, category)" in err


def test_the_gate_itself_reports_it(tmp_path):
    """Wired into validate_method_resolution, which the gate and repair loop run."""
    errors = validate_method_resolution(
        _regenerated("self, term: str, category: str"), _project(tmp_path))
    assert any("changed its signature" in e for e in errors)


def test_renaming_a_parameter_a_caller_passes_by_keyword(tmp_path):
    caller = _CALLER.replace('look_up("value-one")', 'look_up(term="value-one")')
    errors = _signatures_broken_by_regeneration(
        _regenerated("self, query: str"), _project(tmp_path, caller=caller))
    assert len(errors) == 1


def test_a_new_required_keyword_only_parameter(tmp_path):
    errors = _signatures_broken_by_regeneration(
        _regenerated("self, term: str, *, exact: bool"), _project(tmp_path))
    assert len(errors) == 1


def test_removing_a_parameter_a_caller_passes(tmp_path):
    caller = _CALLER.replace('look_up("value-one")', 'look_up("value-one", "value-two")')
    page = _OLD_PAGE.replace("def look_up(self, term: str)",
                             "def look_up(self, term: str, category: str = '')")
    errors = _signatures_broken_by_regeneration(
        _regenerated("self, term: str"), _project(tmp_path, caller=caller, page=page))
    assert len(errors) == 1


# ── what must stay allowed ───────────────────────────────────────────────────

def test_a_new_parameter_with_a_default_is_compatible(tmp_path):
    """The fix the error message asks for must itself pass."""
    assert _signatures_broken_by_regeneration(
        _regenerated("self, term: str, category: str = ''"), _project(tmp_path)) == []


def test_renaming_a_parameter_callers_pass_positionally(tmp_path):
    assert _signatures_broken_by_regeneration(
        _regenerated("self, query: str"), _project(tmp_path)) == []


def test_a_changed_body_with_the_same_signature(tmp_path):
    """Behaviour is not a signature - that is Agent 4's and Agent 3's to judge."""
    assert _signatures_broken_by_regeneration(
        _regenerated("self, term: str", body="        return None\n"),
        _project(tmp_path)) == []


def test_a_call_that_was_already_broken_is_not_this_storys_doing(tmp_path):
    """A defect already on main must never block an unrelated story."""
    caller = _CALLER.replace('look_up("value-one")', 'look_up()')
    assert _signatures_broken_by_regeneration(
        _regenerated("self, term: str, category: str"),
        _project(tmp_path, caller=caller)) == []


def test_a_caller_regenerated_in_the_same_batch_speaks_for_itself(tmp_path):
    root = _project(tmp_path)
    batch = _regenerated("self, term: str, category: str") + [SimpleNamespace(
        file_path="tests/step_defs/test_old_lookup.py", content=_CALLER,
        is_new_file=False)]
    assert _signatures_broken_by_regeneration(batch, root) == []


def test_a_brand_new_page_object_has_nothing_to_compare(tmp_path):
    root = _project(tmp_path)
    new = [SimpleNamespace(file_path="pages/other_page.py",
                           content="class OtherPage:\n    def empty(self, x): ...\n",
                           is_new_file=True)]
    assert _signatures_broken_by_regeneration(new, root) == []


# ── the binding rules themselves ─────────────────────────────────────────────

def _sig(src: str) -> dict:
    return _bindable_signatures(f"class P:\n    def m({src}): ...\n")["P"]["m"]


@pytest.mark.parametrize("signature, positional, keywords, binds", [
    ("self, a",                  1, set(),          True),
    ("self, a",                  0, set(),          False),   # missing
    ("self, a",                  2, set(),          False),   # too many
    ("self, a, b=1",             1, set(),          True),
    ("self, a, b=1",             1, {"b"},          True),
    ("self, a",                  1, {"a"},          False),   # multiple values
    ("self, a",                  0, {"a"},          True),
    ("self, a",                  0, {"z"},          False),   # unexpected keyword
    ("self, a, /",               0, {"a"},          False),   # positional-only
    ("self, *args",              5, set(),          True),
    ("self, **kw",               0, {"anything"},   True),
    ("self, a, *, k",            1, set(),          False),   # missing keyword-only
    ("self, a, *, k",            1, {"k"},          True),
    ("self, a, *, k=0",          1, set(),          True),
])
def test_call_binds_matches_python(signature, positional, keywords, binds):
    assert _call_binds(_sig(signature), positional, keywords) is binds
    # ...and Python agrees, so the rule cannot drift from the language.
    ns: dict = {}
    exec(f"def m({signature}): pass", ns)
    args = [0] * positional
    kwargs = {k: 0 for k in keywords}
    try:
        ns["m"](None, *args, **kwargs)
        python_binds = True
    except TypeError:
        python_binds = False
    assert python_binds is binds
