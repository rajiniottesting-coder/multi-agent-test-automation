"""A story that needs a page the inventory does not have stops at once, and
says how to add it.

3 Nov 2026, SCRUM-284 (Contact Us): the inventory had no contact page. The
page object was refused ("not a page in the app inventory"), the repair loop
"fixed" it by deleting what it could not anchor, the step definitions then
called methods that no longer existed, and after four attempts ($1.50) the
story was blocked with a comment blaming the model and the test case.

No repair can add a page: the inventory is curated by a person. Now the loop
stops before repairing when a generated page object names a page the
inventory lacks - unless it is a misspelling of one it has - and the blocked
comment names the page and the command that adds it. Generic names only.
"""
from unittest.mock import MagicMock, patch

import pytest

from agents.agent2_coder import _attempt_step_coverage_repair
from core import blocked
from core.app_context import AppContext
from core.schemas import CodePlan, FilePlan, GeneratedFile
from validators.method_resolution_validator import pages_missing_from_inventory

PAGES = {"home": {}, "login": {}, "item_detail": {}, "basket": {}}


def _err(page):
    return (f"Selector inventory error in 'pages/{page}_page.py': class XPage sets "
            f"INVENTORY_PAGE = '{page}', which is not a page in the app inventory. "
            "Available pages: basket, home, login, item_detail.")


@pytest.mark.parametrize("errors, missing", [
    ([_err("enquiry")], ["enquiry"]),
    ([_err("enquiry"), _err("enquiry"), _err("faq")], ["enquiry", "faq"]),
    ([_err("item_detial")], []),           # a misspelling: the repair can fix it
    ([_err("basket")], []),                      # known (the inventory changed since)
    (["Method resolution error in 'x': ..."], []),
    ([], []),
])
def test_which_pages_are_missing(errors, missing):
    assert pages_missing_from_inventory(errors, pages=PAGES) == missing


def test_the_shipped_inventory_is_read_when_no_pages_are_given():
    assert pages_missing_from_inventory([_err("zz_not_a_page_anywhere")]) == \
        ["zz_not_a_page_anywhere"]


# ── the repair loop ─────────────────────────────────────────────────────────

@pytest.fixture
def ctx():
    return AppContext(name="TestApp", base_url="https://example.com",
                      inventory_file="app_inventory/test.json",
                      reference_feature="features/ref.feature",
                      reference_step_def="tests/step_defs/test_ref.py",
                      reference_page_object="pages/ref_page.py",
                      reserved_paths=("features/ref.feature",),
                      extendable_paths=("pages/extendable_page.py",))


@pytest.fixture
def plan():
    return CodePlan(feature_name="contact", branch_name="auto/T-1-contact",
                    pr_title="t", pr_body="b",
                    files_to_create=[FilePlan(file_path="pages/enquiry_page.py",
                                              file_type="page_object", purpose="p")])


def _files():
    return [GeneratedFile(file_path="pages/enquiry_page.py", content="class X: pass\n")]


def test_the_loop_spends_nothing_on_a_missing_page(ctx, plan, monkeypatch):
    import agents.agent2_coder as a2
    monkeypatch.setattr(a2, "pages_missing_from_inventory",
                        lambda errors, root=None: pages_missing_from_inventory(errors, pages=PAGES))
    errors = [_err("enquiry"), "Method resolution error in 'tests/step_defs/test_c.py': x"]
    with patch("agents.agent2_coder._collect_repairable_errors", return_value=errors), \
         patch("agents.agent2_coder.generate_file_content") as gen:
        files = _files()
        out = _attempt_step_coverage_repair(files, MagicMock(), plan, [], {}, "{}", ctx)
    gen.assert_not_called()
    assert out == files


def test_a_misspelt_page_is_still_repaired(ctx, monkeypatch):
    import agents.agent2_coder as a2
    monkeypatch.setattr(a2, "pages_missing_from_inventory",
                        lambda errors, root=None: pages_missing_from_inventory(errors, pages=PAGES))
    plan = CodePlan(feature_name="d", branch_name="auto/T-1-d", pr_title="t", pr_body="b",
                    files_to_create=[FilePlan(file_path="pages/item_detial_page.py",
                                              file_type="page_object", purpose="p")])
    calls = iter([[_err("item_detial")], []])
    with patch("agents.agent2_coder._collect_repairable_errors", side_effect=lambda f: next(calls)), \
         patch("agents.agent2_coder.generate_file_content", return_value="class X: pass\n") as gen:
        _attempt_step_coverage_repair(
            [GeneratedFile(file_path="pages/item_detial_page.py", content="class X: pass\n")],
            MagicMock(), plan, [], {}, "{}", ctx, max_retries=2)
    assert gen.call_count == 1


# ── the blocked comment ─────────────────────────────────────────────────────

def test_the_blocked_comment_names_the_page_and_how_to_add_it(monkeypatch):
    import validators.method_resolution_validator as mrv
    monkeypatch.setattr(mrv, "_load_configured_inventory", lambda root=None: {"pages": PAGES})
    text = blocked.blocked_comment("T-1", "0" * 16, [
        "Step coverage error in 'x': ...", _err("enquiry")])
    assert "needs page(s) the app inventory does not have: enquiry" in text
    assert "scripts.plan_inventory page --page" in text
    assert "run Agent 2 with this story's key" in text
    assert "usually means a test case asks" not in text, "not the test case's fault"
    assert text.startswith(f"{blocked.BLOCKED_MARKER} inputs: {'0' * 16}")


def test_other_refusals_read_as_before(monkeypatch):
    import validators.method_resolution_validator as mrv
    monkeypatch.setattr(mrv, "_load_configured_inventory", lambda root=None: {"pages": PAGES})
    text = blocked.blocked_comment("T-1", "0" * 16, ["Step coverage error in 'x': ..."])
    assert "usually means a test case asks" in text and "plan_inventory" not in text
