"""The nightly inventory update: the drift report becomes one reviewed PR.

Before it, the nightly crawl measured stale selectors and uncovered live
elements but nothing ever wrote the inventory: a new feature's elements never
reached it (so Agent 2, which may use inventory keys only, left those test
cases out) and dead selectors stayed for ever.

Every rule below errs toward leaving the inventory alone: a key code names is
never removed, a page that did not render as itself is never edited, a branch a
person committed to is never replaced. Fake inventory and host; no application
names.
"""
import copy
import json
from pathlib import Path

import pytest
import yaml

from core import inventory_update as iu

ROOT = Path(__file__).resolve().parents[2]
INV_PATH = "app_inventory/app.json"


def _inventory():
    return {
        "app_name": "Example",
        "pages": {
            "account": {
                "url": "/account",
                "row_family": "order_rows",
                "multi_match": ["order_rows", "old_banner"],
                "conditional": ["old_banner", "saved_message"],
                "elements_notes": {"old_banner": "Shown after sign-up.", "_naming": "x"},
                "elements": {
                    "save_button": "role=button[name='Save']",
                    "old_banner": ".banner-legacy",
                    "order_rows": "tr.order",
                    "email_input": "#email",
                    "saved_message": "text=Saved",
                    "_note": "not a selector",
                },
            },
            "search": {
                "url": "/search",
                "elements": {"query_input": "#q", "go_button": "#go",
                             "result_cards": ".card", "filter_link": "text=Filter"},
            },
        },
    }


def _drift(pages, new=None, unreachable=()):
    out = {"pages_checked": len(pages), "unreachable_pages": list(unreachable),
           "checked_at": "2026-10-27T01:45:00+00:00", "pages": {}}
    for name, missing in pages.items():
        inv = _inventory()["pages"][name]["elements"]
        out["pages"][name] = {"missing": [{"element": k, "selector": inv[k]} for k in missing],
                              "new_data_tests": [], "ambiguous": []}
    if new is not None:
        out["new_elements"] = new
    return out


USED = {"save_button", "email_input", "query_input", "go_button", "result_cards"}


# ── what changes ────────────────────────────────────────────────────────

def test_a_changed_selector_is_replaced_and_the_key_kept():
    inv = _inventory()
    upd = iu.build_update(_drift({"account": ["save_button"]},
                                 {"account": {"save_button": "role=button[name='Save changes']"}}),
                          inv, USED)
    assert upd.replaced == [{"page": "account", "element": "save_button",
                             "old": "role=button[name='Save']",
                             "new": "role=button[name='Save changes']"}]
    assert upd.inventory["pages"]["account"]["elements"]["save_button"] == \
        "role=button[name='Save changes']"
    assert not upd.added and not upd.removed
    assert inv == _inventory(), "the input inventory is never modified"


def test_a_stale_key_no_code_names_is_removed_with_every_reference():
    upd = iu.build_update(_drift({"account": ["old_banner"]}), _inventory(), USED)
    page = upd.inventory["pages"]["account"]
    assert upd.removed == [{"page": "account", "element": "old_banner",
                            "selector": ".banner-legacy"}]
    assert "old_banner" not in page["elements"]
    assert "old_banner" not in page["elements_notes"] and "_naming" in page["elements_notes"]
    assert page["multi_match"] == ["order_rows"] and page["conditional"] == ["saved_message"]
    assert page["elements"]["_note"] == "not a selector"


def test_a_stale_key_code_still_names_is_kept_for_a_person():
    upd = iu.build_update(_drift({"account": ["email_input"]}), _inventory(), USED)
    assert not upd.changed
    assert upd.kept_missing[0]["element"] == "email_input"
    assert "code still names it" in upd.kept_missing[0]["why"]


def test_the_row_family_is_kept_even_when_no_code_names_it():
    upd = iu.build_update(_drift({"account": ["order_rows"]}), _inventory(), set())
    assert not upd.removed and upd.kept_missing[0]["why"] == "the page's row family"


def test_a_page_that_did_not_render_as_itself_is_left_alone():
    drift = _drift({"search": ["query_input", "go_button", "filter_link"]},
                   {"search": {"error_heading": "text=Something went wrong"}})
    upd = iu.build_update(drift, _inventory(), set(), hold_ratio=0.5)
    assert upd.held_pages == [{"page": "search", "stale": 3, "total": 4}]
    assert not upd.changed, "no removal and no addition from an error page"


def test_one_stale_key_on_a_small_page_is_not_a_held_page():
    inv = _inventory()
    inv["pages"]["search"]["elements"] = {"query_input": "#q", "filter_link": "text=Filter"}
    upd = iu.build_update(_drift({"search": ["filter_link"]}), inv, USED)
    assert not upd.held_pages and upd.removed[0]["element"] == "filter_link"


def test_new_elements_are_added_within_the_limit_and_refused_by_the_shared_rules():
    new = {"account": {"phone_input": "#phone", "zip_input": "#zip", "city_input": "#city",
                       "email_input": "#email-2",          # name taken
                       "copy_of_save": "role=button[name='Save']",   # selector taken
                       "Bad-Name": "#bad"}}
    upd = iu.build_update(_drift({"account": []}, new), _inventory(), USED,
                          max_additions_per_page=2)
    assert [r["element"] for r in upd.added] == ["city_input", "phone_input"]
    assert [r["element"] for r in upd.over_cap] == ["zip_input"]
    assert {r["element"] for r in upd.refused} == {"email_input", "copy_of_save", "Bad-Name"}
    assert upd.inventory["pages"]["account"]["elements"]["city_input"] == "#city"


def test_ambiguous_unreachable_and_test_ids_are_reported_never_changed():
    drift = _drift({"account": []}, {}, unreachable=["checkout"])
    drift["pages"]["account"]["ambiguous"] = [{"element": "save_button",
                                               "selector": "x", "matches": 3}]
    drift["pages"]["account"]["new_data_tests"] = ["promo"]
    upd = iu.build_update(drift, _inventory(), USED)
    assert not upd.changed
    assert upd.ambiguous[0]["matches"] == 3 and upd.unreachable == ["checkout"]
    assert upd.new_test_ids == [{"page": "account", "value": "promo"}]


def test_without_compare_nothing_is_added_or_replaced():
    upd = iu.build_update(_drift({"account": ["save_button"]}), _inventory(), USED)
    assert not upd.replaced and not upd.added and upd.kept_missing


# ── which keys code names ───────────────────────────────────────────────

def test_keys_named_in_code_reads_every_string_literal(tmp_path):
    (tmp_path / "pages").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pages" / "a.py").write_text(
        "KEY = 'via_constant'\nclass A:\n    def go(self):\n        self.click(self.sel('direct'))\n")
    (tmp_path / "tests" / "broken.py").write_text("def x(:\n  y = \"from_broken_file\"\n")
    (tmp_path / "other.py").write_text("'outside_code_dirs'\n")
    found = iu.keys_named_in_code(tmp_path, ["pages", "tests"])
    assert {"via_constant", "direct", "from_broken_file"} <= found
    assert "outside_code_dirs" not in found


def test_the_real_code_names_every_key_the_page_objects_use():
    used = iu.keys_named_in_code(ROOT, ["pages", "tests"])
    from validators.method_resolution_validator import _sel_keys_in
    import ast
    for path in (ROOT / "pages").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef):
                assert set(_sel_keys_in(node)) <= used, path


# ── text and body ───────────────────────────────────────────────────────

def test_the_file_keeps_its_own_format_so_the_diff_shows_only_changes():
    inv = _inventory()
    with_nl = json.dumps(inv, indent=2, ensure_ascii=False) + "\n"
    without = with_nl[:-1]
    assert iu.dump_like(with_nl, inv) == with_nl and iu.dump_like(without, inv) == without
    inv["app_name"] = "Exämple — ü"
    assert "Exämple — ü" in iu.dump_like(with_nl, inv), "non-ASCII is kept as written"


def test_the_body_carries_the_marker_and_only_the_sections_with_rows():
    upd = iu.build_update(_drift({"account": ["old_banner", "email_input"]},
                                 {"account": {"phone_input": "#phone"}}), _inventory(), USED)
    body = iu.render_body(upd, INV_PATH, "abcdef123456", "2026-10-27")
    assert body.startswith(f"{iu.MARKER} content: abcdef123456")
    assert "Added - live elements" in body and "`account.phone_input`" in body
    assert "Removed - no longer on the page" in body and "Kept although not found" in body
    assert "Selectors replaced" not in body and "Pages not changed" not in body
    assert "Nothing is merged by an agent" in body


def test_the_branch_may_not_carry_an_issue_key():
    with pytest.raises(ValueError):
        iu.settings({"branch": "inventory/ABC-12-update"})
    assert iu.settings({})["branch"] == iu.DEFAULTS["branch"]


# ── the pull request ────────────────────────────────────────────────────

class FakeHost:
    def __init__(self, open_pr=None, branch_text=None, comments=()):
        self.prs = [open_pr] if open_pr else []
        self.files = {INV_PATH: branch_text} if branch_text is not None else {}
        self.branches = {"inventory-update/nightly"} if open_pr else set()
        self.comments = list(comments)
        self.log = []

    def list_open_prs(self, prefix=""):
        return [p for p in self.prs if p["head_ref"].startswith(prefix)]
    def get_pr_metadata(self, n): return {"body": self.prs[0]["body"]}
    def get_file_content(self, path, branch="main"):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]
    def get_pr_comments(self, n): return list(self.comments)
    def post_pr_comment(self, n, body):
        self.comments.append(body)
        self.log.append(("comment", n))
    def branch_exists(self, b): return b in self.branches
    def delete_branch(self, b):
        self.branches.discard(b)
        self.prs = []
        self.log.append(("delete", b))
        return True
    def create_branch(self, b, from_branch="main"):
        self.branches.add(b)
        self.log.append(("branch", b, from_branch))
    def create_or_update_file(self, path, content, msg, branch):
        if getattr(self, "fail_write", False):
            raise RuntimeError("write refused")
        self.files[path] = content
        self.log.append(("write", path, branch))
    def open_pull_request(self, title, body, head, base):
        self.prs = [{"number": 9, "head_ref": head, "body": body}]
        self.log.append(("pr", title, head, base))
        return "https://example/pr/9"


ORIGINAL = json.dumps(_inventory(), indent=2, ensure_ascii=False) + "\n"
BRANCH = "inventory-update/nightly"


def _change():
    return iu.build_update(_drift({"account": ["old_banner"]}), _inventory(), USED)


def _refresh(host, upd):
    return iu.open_or_refresh(host, upd, inventory_path=INV_PATH, original=ORIGINAL,
                              branch=BRANCH, today="2026-10-27")


def _pr_for(upd):
    text = iu.dump_like(ORIGINAL, upd.inventory)
    body = iu.render_body(upd, INV_PATH, iu.content_hash(text))
    return {"number": 7, "head_ref": BRANCH, "body": body}, text


def test_a_change_opens_one_pull_request_from_main():
    host = FakeHost()
    out = _refresh(host, _change())
    assert out == {"status": "opened", "url": "https://example/pr/9"}
    assert host.log[0] == ("branch", BRANCH, "main")
    assert ("write", INV_PATH, BRANCH) in host.log
    assert "old_banner" not in json.loads(host.files[INV_PATH])["pages"]["account"]["elements"]


def test_no_change_and_no_pull_request_does_nothing():
    host = FakeHost()
    out = _refresh(host, iu.build_update(_drift({"account": []}), _inventory(), USED))
    assert out == {"status": "nothing_to_change"} and host.log == []


def test_the_same_proposal_again_leaves_the_open_pull_request_alone():
    upd = _change()
    pr, text = _pr_for(upd)
    host = FakeHost(pr, text)
    assert _refresh(host, upd) == {"status": "unchanged", "pr": 7} and host.log == []


def test_a_different_proposal_supersedes_an_untouched_pull_request():
    old = iu.build_update(_drift({"account": ["old_banner"]}), _inventory(), USED)
    pr, text = _pr_for(old)
    host = FakeHost(pr, text)
    new = iu.build_update(_drift({"account": ["old_banner"]},
                                 {"account": {"phone_input": "#phone"}}), _inventory(), USED)
    out = _refresh(host, new)
    assert out["status"] == "opened"
    assert [e[0] for e in host.log] == ["comment", "delete", "branch", "write", "pr"]
    assert "a fresh pull request replaces this one" in host.comments[0]


def test_nothing_to_change_closes_an_untouched_pull_request():
    pr, text = _pr_for(_change())
    host = FakeHost(pr, text)
    out = _refresh(host, iu.build_update(_drift({"account": []}), _inventory(), USED))
    assert out == {"status": "closed"}
    assert [e[0] for e in host.log] == ["comment", "delete"]
    assert "needs no change now" in host.comments[0]


def test_a_branch_a_person_edited_is_never_replaced_and_noted_once():
    upd = _change()
    pr, text = _pr_for(upd)
    host = FakeHost(pr, text.replace("Save", "Store"))       # a person's commit
    other = iu.build_update(_drift({"account": ["old_banner"]},
                                   {"account": {"phone_input": "#phone"}}), _inventory(), USED)
    assert _refresh(host, other)["status"] == "kept_edited"
    assert _refresh(host, other)["status"] == "kept_edited"
    assert [e[0] for e in host.log] == ["comment"], "one note per finding, no replacement"
    assert "edited by a person" in host.comments[0]


def test_a_failed_write_leaves_no_half_written_branch():
    host = FakeHost()
    host.fail_write = True
    with pytest.raises(RuntimeError):
        _refresh(host, _change())
    assert host.log[-1] == ("delete", BRANCH) and BRANCH not in host.branches


def test_a_leftover_branch_without_a_pull_request_is_replaced():
    host = FakeHost()
    host.branches.add(BRANCH)
    assert _refresh(host, _change())["status"] == "opened"
    assert host.log[0] == ("delete", BRANCH)


# ── the script and the workflow ─────────────────────────────────────────

def test_a_crawl_that_measured_nothing_proposes_and_closes_nothing(tmp_path, capsys, monkeypatch):
    from scripts import propose_inventory_update as script
    report = tmp_path / "drift.json"
    report.write_text(json.dumps({"pages_checked": 0, "pages": {}}))
    monkeypatch.setattr("integrations.repo_host.get_repo_host",
                        lambda *a, **k: pytest.fail("no host call on an empty crawl"))
    assert script.main(["--drift-report", str(report)]) == 0
    assert "measured no page" in capsys.readouterr().out


def test_a_dry_run_prints_the_body_and_never_reaches_the_host(tmp_path, capsys, monkeypatch):
    from scripts import propose_inventory_update as script
    inv_file = "app_inventory/app.json"
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / inv_file).write_text(ORIGINAL, encoding="utf-8")
    report = tmp_path / "drift.json"
    report.write_text(json.dumps(_drift({"account": ["old_banner"]})))
    monkeypatch.setattr(script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(script, "impact_settings", lambda: {"shadow_mode": False})
    monkeypatch.setattr(script.AppContext, "load",
                        classmethod(lambda cls: type("C", (), {"inventory_file": inv_file})()))
    monkeypatch.setattr("integrations.repo_host.get_repo_host",
                        lambda *a, **k: pytest.fail("a dry run never reaches the host"))
    assert script.main(["--drift-report", str(report), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "removed 1" in out and iu.MARKER in out and "`account.old_banner`" in out


def test_shadow_mode_prints_and_never_reaches_the_host(tmp_path, capsys, monkeypatch):
    from scripts import propose_inventory_update as script
    inv_file = "app_inventory/app.json"
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / inv_file).write_text(ORIGINAL, encoding="utf-8")
    report = tmp_path / "drift.json"
    report.write_text(json.dumps(_drift({"account": ["old_banner"]})))
    monkeypatch.setattr(script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(script, "impact_settings", lambda: {"shadow_mode": True})
    monkeypatch.setattr(script.AppContext, "load",
                        classmethod(lambda cls: type("C", (), {"inventory_file": inv_file})()))
    monkeypatch.setattr("integrations.repo_host.get_repo_host",
                        lambda *a, **k: pytest.fail("shadow mode never reaches the host"))
    assert script.main(["--drift-report", str(report)]) == 0
    assert "Agent 0 shadow mode: nothing written" in capsys.readouterr().out


def test_the_drift_job_proposes_the_update_after_its_analysis():
    wf = yaml.safe_load((ROOT / ".github/workflows/agent0_impact.yml").read_text(encoding="utf-8"))
    steps = wf["jobs"]["drift"]["steps"]
    names = [s.get("name", "") for s in steps]
    i = names.index("Propose the inventory update as a pull request")
    assert i > names.index("Check the inventory, then analyse the drift")
    step = steps[i]
    assert step["if"] == "always()"
    assert "scripts.propose_inventory_update" in step["run"] and "--dry-run" in step["run"]
    assert step["env"]["GITHUB_TOKEN"] == "${{ secrets.GH_PAT }}"


def test_config_and_defaults_agree():
    cfg = yaml.safe_load((ROOT / "config/config.yaml").read_text(encoding="utf-8"))
    block = cfg["agents"]["agent0_impact"]["inventory_update"]
    merged = iu.settings(block)
    assert merged["branch"] == iu.DEFAULTS["branch"] and merged["enabled"] is True
    assert set(block) <= set(iu.DEFAULTS)
