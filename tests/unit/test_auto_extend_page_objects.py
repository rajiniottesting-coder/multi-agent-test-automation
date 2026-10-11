"""Committed page objects are extendable automatically, and keep their methods.

Before this, a page object one story merged was Tier-3 NEW to the next story
unless someone listed it in extendable_paths by hand. The next story then
regenerated it whole and could drop a method the first story's tests call.

Covers the three parts of the change:
  - discovery: every committed pages/*_page.py, minus reserved and base_page
  - plan correction: an existing page object planned as "new" is extended
  - contract: a removed or re-signatured method is refused, through the repair
    loop's error format

Generic names only; no network, no model.
"""
import textwrap
from pathlib import Path

import pytest

import agents.agent2_coder as a2
from core import app_context
from core.app_context import AppContext, discover_page_objects
from core.schemas import CodePlan, FilePlan, GeneratedFile
from validators.page_object_contract import validate_extended_page_objects_keep_methods


def _w(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


# ─────────────────────────────────────────────────────────────
# Discovery
# ─────────────────────────────────────────────────────────────

def test_committed_page_objects_are_found_minus_reserved_and_base(tmp_path):
    for name in ("base_page.py", "login_page.py", "widget_page.py", "gadget_page.py",
                 "helpers.py", "__init__.py"):
        _w(tmp_path, f"pages/{name}", "x = 1\n")
    found = discover_page_objects(tmp_path / "pages", tmp_path, {"pages/login_page.py"})
    assert found == ["pages/gadget_page.py", "pages/widget_page.py"]


def test_no_pages_directory_finds_nothing(tmp_path):
    assert discover_page_objects(tmp_path / "pages", tmp_path, set()) == []


_CONFIG = """
app_under_test:
  name: "Sample"
  base_url: "https://app.example"
  inventory_file: "inv.json"
  reference_files:
    feature: "features/ref.feature"
    step_def: "tests/step_defs/test_ref.py"
    page_object: "pages/ref_page.py"
  reserved_paths: ["pages/ref_page.py"]
  extendable_paths: ["./pages/listed_page.py"]
  {flag}
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    for name in ("base_page.py", "ref_page.py", "widget_page.py", "listed_page.py"):
        _w(tmp_path, f"pages/{name}", "x = 1\n")
    monkeypatch.setattr(app_context, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(app_context, "PAGES_DIR", tmp_path / "pages")
    return tmp_path


def test_load_adds_committed_page_objects_to_the_configured_list(repo):
    cfg = _w(repo, "config.yaml", _CONFIG.format(flag=""))
    ctx = AppContext.load(cfg)
    assert ctx.extendable_paths == ("pages/listed_page.py", "pages/widget_page.py")
    assert "pages/ref_page.py" not in ctx.extendable_paths      # reserved stays out


def test_the_automatic_rule_can_be_switched_off(repo):
    cfg = _w(repo, "config.yaml", _CONFIG.format(flag="auto_extend_page_objects: false"))
    assert AppContext.load(cfg).extendable_paths == ("./pages/listed_page.py",)


def test_this_repository_adds_nothing_today():
    """Only reserved page objects and base_page are on main now, so behaviour is
    unchanged until a story merges its first page object."""
    ctx = AppContext.load()
    assert not set(ctx.extendable_paths) & ctx.reserved_paths_normalized()
    for path in ctx.extendable_paths:
        assert (app_context.PROJECT_ROOT / path).is_file()


# ─────────────────────────────────────────────────────────────
# Plan correction
# ─────────────────────────────────────────────────────────────

def _plan(*paths_new):
    return CodePlan(
        feature_name="x", branch_name="auto/X-1-x", pr_title="t", pr_body="b",
        files_to_create=[FilePlan(file_path=p, file_type="page_object", purpose="p",
                                  is_new_file=new) for p, new in paths_new])


def _ctx(extendable):
    return AppContext(name="Sample", base_url="https://app.example", inventory_file="inv.json",
                      reference_feature="f", reference_step_def="s",
                      reference_page_object="pages/ref_page.py",
                      reserved_paths=("pages/ref_page.py",), extendable_paths=tuple(extendable))


def test_an_existing_page_object_planned_as_new_is_extended_instead(tmp_path):
    _w(tmp_path, "pages/widget_page.py", "x = 1\n")
    plan = _plan(("pages/widget_page.py", True), ("pages/fresh_page.py", True))
    corrected = a2._extend_existing_page_objects(plan, _ctx(["pages/widget_page.py"]), tmp_path)
    assert corrected == ["pages/widget_page.py"]
    assert [fp.is_new_file for fp in plan.files_to_create] == [False, True]


def test_the_corrected_plan_passes_the_path_policy(tmp_path):
    _w(tmp_path, "pages/widget_page.py", "x = 1\n")
    plan = _plan(("pages/widget_page.py", True))
    ctx = _ctx(["pages/widget_page.py"])
    a2._extend_existing_page_objects(plan, ctx, tmp_path)
    a2.validate_paths_against_policy(plan, ctx)                 # no exception


def test_a_listed_file_that_does_not_exist_still_stops_the_run(tmp_path):
    """A configuration mistake stays visible: nothing to extend, nothing corrected."""
    plan = _plan(("pages/not_yet_page.py", True))
    ctx = _ctx(["pages/not_yet_page.py"])
    assert a2._extend_existing_page_objects(plan, ctx, tmp_path) == []
    with pytest.raises(ValueError, match="marked existing extendable"):
        a2.validate_paths_against_policy(plan, ctx)


# ─────────────────────────────────────────────────────────────
# Contract: methods are kept
# ─────────────────────────────────────────────────────────────

COMMITTED = '''
class WidgetPage:
    def open(self):
        pass
    def remove_product(self, name):
        pass
    def quantity_of(self, name, row=0):
        pass
    def _helper(self):
        pass
'''


@pytest.fixture
def committed(tmp_path):
    _w(tmp_path, "pages/widget_page.py", COMMITTED)
    return tmp_path


def _check(root, content, path="pages/widget_page.py"):
    return validate_extended_page_objects_keep_methods(
        [GeneratedFile(file_path=path, content=textwrap.dedent(content))], root)


def test_adding_methods_is_fine(committed):
    assert _check(committed, COMMITTED + "    def total(self):\n        pass\n") == []


def test_a_removed_method_is_refused_and_named(committed):
    errors = _check(committed, '''
        class WidgetPage:
            def open(self):
                pass
            def quantity_of(self, name, row=0):
                pass
    ''')
    assert len(errors) == 1
    assert errors[0].startswith("Removed method error in 'pages/widget_page.py':")
    assert "WidgetPage.remove_product(name) was removed" in errors[0]


def test_a_private_helper_may_go(committed):
    assert _check(committed, COMMITTED.replace("    def _helper(self):\n        pass\n", "")) == []


def test_a_changed_parameter_list_is_refused(committed):
    errors = _check(committed, COMMITTED.replace("remove_product(self, name)",
                                                 "remove_product(self, product)"))
    assert "remove_product changed its parameters from (name) to (product)" in errors[0]


def test_a_new_last_parameter_with_a_default_is_fine(committed):
    content = COMMITTED.replace("remove_product(self, name)", "remove_product(self, name, confirm=True)")
    assert _check(committed, content) == []


def test_a_new_required_parameter_is_refused_even_after_a_default(committed):
    """quantity_of already has a default; a new parameter without one still breaks calls."""
    content = COMMITTED.replace("quantity_of(self, name, row=0)",
                                "quantity_of(self, name, row=0, *, unit)")
    assert "quantity_of changed its parameters" in _check(committed, content)[0]


def test_a_removed_class_reports_every_method(committed):
    errors = _check(committed, "class Other:\n    pass\n")
    for name in ("open", "remove_product", "quantity_of"):
        assert f"WidgetPage.{name}(" in errors[0]


def test_a_new_page_object_is_not_checked(committed):
    assert _check(committed, "class New:\n    pass\n", path="pages/fresh_page.py") == []


def test_non_page_files_and_base_page_are_not_checked(committed):
    _w(committed, "pages/base_page.py", "class BasePage:\n    def click(self):\n        pass\n")
    assert _check(committed, "", path="pages/base_page.py") == []
    assert _check(committed, "", path="tests/step_defs/test_x.py") == []


def test_unparseable_content_is_left_to_the_syntax_check(committed):
    assert _check(committed, "class WidgetPage(:\n") == []


def test_the_error_is_routed_to_its_own_repair_hint(committed):
    errors = _check(committed, "class WidgetPage:\n    pass\n")
    assert a2._classify_error(errors[0]) == "removed_method"
    assert "Keep EVERY existing method" in a2._build_error_type_guidance(errors)
