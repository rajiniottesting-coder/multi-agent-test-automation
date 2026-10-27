"""The nightly inventory update: the drift report becomes one reviewed PR.

Before it, the nightly crawl measured stale selectors and uncovered live
elements but nothing ever wrote the inventory: a new feature's elements never
reached it (so Agent 2, which may use inventory keys only, left those test
cases out) and dead selectors stayed for ever.

Every rule below errs toward leaving the inventory alone: a key code names -
on main or in an open pull request - is never removed, a page that did not
render as itself is never edited, an element without a durable handle is never
added, a proposal a person committed to is never replaced, and an old or empty
crawl changes nothing. Fake inventory and host; no application names.
"""
import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from core import inventory_update as iu

ROOT = Path(__file__).resolve().parents[2]
INV_PATH = "app_inventory/app.json"
PREFIX = "inventory-update/"
NOW = datetime(2026, 10, 27, 2, 0, tzinfo=timezone.utc)


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
                    "structured": {"selector": "#s"},
                },
            },
            "search": {
                "url": "/search",
                "elements": {"query_input": "#q", "go_button": "#go",
                             "result_cards": ".card", "filter_link": "text=Filter"},
            },
        },
    }


def _drift(pages, new=None, declared=None, unreachable=(), checked_at=NOW.isoformat()):
    out = {"pages_checked": len(pages), "unreachable_pages": list(unreachable),
           "checked_at": checked_at, "pages": {}}
    for name, missing in pages.items():
        inv = _inventory()["pages"].get(name, {}).get("elements", {})
        out["pages"][name] = {"missing": [{"element": k, "selector": inv.get(k, "?")}
                                          for k in missing],
                              "new_data_tests": [], "ambiguous": []}
    if new is not None:
        out["new_elements"] = new
    if declared is not None:
        out["new_element_declarations"] = declared
    return out


USED = {"save_button", "email_input", "query_input", "go_button", "result_cards"}


# ── replace ─────────────────────────────────────────────────────────────

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


def test_a_replacement_carries_the_generators_declaration():
    upd = iu.build_update(
        _drift({"account": ["email_input"]}, {"account": {"email_input": "#mail"}},
               {"account": {"conditional": ["email_input"]}}), _inventory(), USED)
    assert upd.replaced and "email_input" in upd.inventory["pages"]["account"]["conditional"]


def test_a_replacement_whose_selector_another_key_holds_is_refused_and_listed():
    upd = iu.build_update(_drift({"account": ["email_input"]},
                                 {"account": {"email_input": "role=button[name='Save']"}}),
                          _inventory(), USED)
    assert not upd.replaced
    assert upd.refused[0]["element"] == "email_input"
    assert "already used" in upd.refused[0]["refused"]
    assert upd.kept_missing[0]["element"] == "email_input", "still kept: code names it"


def test_a_replacement_with_no_durable_handle_is_never_made():
    upd = iu.build_update(
        _drift({"account": ["email_input"]}, {"account": {"email_input": "div > span"}},
               {"account": {"unstable": ["email_input"]}}), _inventory(), USED)
    assert not upd.replaced and upd.fragile[0]["element"] == "email_input"


# ── remove / keep ───────────────────────────────────────────────────────

def test_a_stale_key_no_code_names_is_removed_with_every_reference():
    upd = iu.build_update(_drift({"account": ["old_banner"]}), _inventory(), USED)
    page = upd.inventory["pages"]["account"]
    assert upd.removed == [{"page": "account", "element": "old_banner",
                            "selector": ".banner-legacy"}]
    assert "old_banner" not in page["elements"]
    assert "old_banner" not in page["elements_notes"] and "_naming" in page["elements_notes"]
    assert page["multi_match"] == ["order_rows"] and page["conditional"] == ["saved_message"]
    assert page["elements"]["_note"] == "not a selector"
    assert page["elements"]["structured"] == {"selector": "#s"}


def test_a_stale_key_code_on_main_names_is_kept_for_a_person():
    upd = iu.build_update(_drift({"account": ["email_input"]}), _inventory(), USED)
    assert not upd.changed
    assert upd.kept_missing[0]["why"] == "code still names it"


def test_a_stale_key_only_an_open_pull_request_names_is_kept():
    """A story in flight adds a page object method using the key: removing it
    would break that story after both merge."""
    files = [{"filename": "pages/account_page.py",
              "patch": "@@ -1 +1,3 @@\n+    def ban(self):\n+        return self.sel('old_banner')\n"}]
    in_flight = iu.keys_in_patches(files)
    upd = iu.build_update(_drift({"account": ["old_banner"]}), _inventory(), USED | in_flight)
    assert not upd.removed and upd.kept_missing[0]["element"] == "old_banner"


def test_nothing_is_removed_when_the_open_pull_requests_could_not_be_read():
    upd = iu.build_update(_drift({"account": ["old_banner"]}), _inventory(), USED,
                          allow_removal=False,
                          no_removal_reason="open pull requests could not be checked")
    assert not upd.removed
    assert upd.kept_missing[0]["why"] == "open pull requests could not be checked"


@pytest.mark.parametrize("family", ["order_rows", ["order_rows", "x"]])
def test_the_row_family_is_kept_even_when_no_code_names_it(family):
    inv = _inventory()
    inv["pages"]["account"]["row_family"] = family
    upd = iu.build_update(_drift({"account": ["order_rows"]}), inv, set())
    assert not upd.removed and upd.kept_missing[0]["why"] == "the page's row family"


# ── hold ────────────────────────────────────────────────────────────────

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


# ── add ─────────────────────────────────────────────────────────────────

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


def test_an_added_family_or_hidden_element_carries_its_declaration():
    """Without it a family reads as ambiguous and a hidden element as stale the
    next night - and an unused stale key would be removed again (flip-flop)."""
    new = {"account": {"tag_chips": ".chip", "help_tip": "#tip"}}
    declared = {"account": {"multi_match": ["tag_chips"], "conditional": ["help_tip"]}}
    upd = iu.build_update(_drift({"account": []}, new, declared), _inventory(), USED)
    page = upd.inventory["pages"]["account"]
    assert "tag_chips" in page["multi_match"] and "help_tip" in page["conditional"]
    nxt = iu.build_update(_drift({"account": []}), upd.inventory, USED)
    assert not nxt.changed, "the next night finds nothing to undo"


def test_an_element_with_no_durable_handle_is_listed_never_added():
    new = {"account": {"card_1_link": "a.card >> nth=0", "card_2_link": "a.card >> nth=1",
                       "phone_input": "#phone"}}
    declared = {"account": {"unstable": ["card_1_link", "card_2_link"]}}
    upd = iu.build_update(_drift({"account": []}, new, declared), _inventory(), USED)
    assert [r["element"] for r in upd.added] == ["phone_input"]
    assert [r["element"] for r in upd.fragile] == ["card_1_link", "card_2_link"]


def test_a_page_object_missing_from_the_inventory_is_ignored():
    drift = _drift({"account": []})
    drift["pages"]["checkout"] = {"missing": [{"element": "x", "selector": "#x"}]}
    drift["new_elements"] = {"checkout": {"pay_button": "#pay"}}
    assert not iu.build_update(drift, _inventory(), USED).changed


# ── report only ─────────────────────────────────────────────────────────

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
    for path in (ROOT / "pages").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef):
                assert set(_sel_keys_in(node)) <= used, path


def test_keys_in_patches_reads_only_added_python_lines_in_the_code_directories():
    files = [{"filename": "pages/a.py", "patch": "+x = 'added'\n- y = 'removed'\n x = 'context'"},
             {"filename": "docs/a.py", "patch": "+'outside'"},
             {"filename": "pages/a.md", "patch": "+'not_python'"},
             {"filename": "tests/b.py", "patch": None}]
    assert iu.keys_in_patches(files) == {"added"}


class _OpenPRs:
    def __init__(self, fail=False):
        self.fail, self.read = fail, []
    def list_open_prs(self, prefix="", strict=False):
        assert strict, "an unreadable list must never read as an empty one"
        if self.fail:
            raise RuntimeError("API down")
        return [{"number": 1, "head_ref": "auto/S-1-x"}, {"number": 2, "head_ref": PREFIX + "d"}]
    def get_pr_changed_files(self, n):
        self.read.append(n)
        return [{"filename": "pages/p.py", "patch": f"+k = 'key_from_{n}'"}]


def test_keys_named_in_open_prs_skips_its_own_proposals_and_fails_safe():
    host = _OpenPRs()
    assert iu.keys_named_in_open_prs(host, own_prefix=PREFIX) == {"key_from_1"}
    assert host.read == [1]
    assert iu.keys_named_in_open_prs(_OpenPRs(fail=True)) is None


# ── report freshness, file format, body, settings ───────────────────────

def test_an_old_or_undated_report_is_refused():
    assert iu.report_age_problem({"checked_at": NOW.isoformat()}, 48, NOW) == ""
    old = (NOW - timedelta(hours=49)).isoformat()
    assert "49 h old" in iu.report_age_problem({"checked_at": old}, 48, NOW)
    assert "no checked_at" in iu.report_age_problem({}, 48, NOW)
    naive = (NOW - timedelta(hours=1)).replace(tzinfo=None).isoformat()
    assert iu.report_age_problem({"checked_at": naive}, 48, NOW) == ""


def test_the_file_keeps_its_own_format_so_the_diff_shows_only_changes():
    inv = _inventory()
    with_nl = json.dumps(inv, indent=2, ensure_ascii=False) + "\n"
    without = with_nl[:-1]
    assert iu.dump_like(with_nl, inv) == with_nl and iu.dump_like(without, inv) == without
    inv["app_name"] = "Exämple — ü"
    assert "Exämple — ü" in iu.dump_like(with_nl, inv), "non-ASCII is kept as written"


def test_the_real_inventory_round_trips_byte_for_byte():
    from core.app_context import AppContext
    path = ROOT / AppContext.load().inventory_file
    text = path.read_text(encoding="utf-8")
    assert iu.dump_like(text, json.loads(text)) == text


def test_the_body_carries_the_marker_and_only_the_sections_with_rows():
    upd = iu.build_update(_drift({"account": ["old_banner", "email_input"]},
                                 {"account": {"phone_input": "#phone"}}), _inventory(), USED)
    body = iu.render_body(upd, INV_PATH, "abcdef123456", "2026-10-27")
    assert body.startswith(f"{iu.MARKER} content: abcdef123456")
    assert "Added - live elements" in body and "`account.phone_input`" in body
    assert "Removed - no longer on the page" in body and "declared `conditional`" in body
    assert "Kept although not found" in body
    assert "Selectors replaced" not in body and "Pages not changed" not in body
    assert "Nothing is merged by an agent" in body


def test_the_body_stays_within_the_hosts_limit():
    upd = iu.InventoryUpdate(inventory={})
    upd.over_cap = [{"page": "p", "element": f"e{i}", "selector": "x" * 80} for i in range(500)]
    upd.refused = [{**r, "refused": "y" * 80} for r in upd.over_cap]
    upd.fragile = list(upd.over_cap)
    body = iu.render_body(upd, INV_PATH, "abcdef123456")
    assert len(body) < 65_536
    rows = [l for l in body.splitlines() if l.startswith("| `p.e")]
    assert len(rows) == 3 * 60, "every table shows at most 60 rows"
    assert body.count("and 440 more") == 3, "and counts the rest"
    assert "truncated" not in body, "the caps keep every table whole"


def test_the_branch_prefix_may_not_carry_an_issue_key():
    with pytest.raises(ValueError):
        iu.settings({"branch_prefix": "inventory/ABC-12-"})
    assert iu.settings({})["branch_prefix"] == iu.DEFAULTS["branch_prefix"]


# ── the pull request ────────────────────────────────────────────────────

class FakeHost:
    def __init__(self, prs=(), files=None, comments=None):
        self.prs = [dict(p) for p in prs]
        self.files = dict(files or {})            # {(branch, path): text}
        self.branches = {p["head_ref"] for p in self.prs}
        self.comments = {p["number"]: [] for p in self.prs} | dict(comments or {})
        self.log, self.fail_write, self.fail_delete = [], False, False

    def list_open_prs(self, prefix="", strict=False):
        assert strict, "an unreadable list must never read as 'no proposal open'"
        return [p for p in self.prs if p["head_ref"].startswith(prefix)]
    def get_pr_metadata(self, n): return {"body": next(p for p in self.prs if p["number"] == n)["body"]}
    def get_file_content(self, path, branch="main"):
        if (branch, path) not in self.files:
            raise FileNotFoundError(path)
        return self.files[(branch, path)]
    def get_pr_comments(self, n): return list(self.comments.get(n, []))
    def post_pr_comment(self, n, body):
        self.comments.setdefault(n, []).append(body)
        self.log.append(("comment", n))
    def close_pull_request(self, n):
        self.prs = [p for p in self.prs if p["number"] != n]
        self.log.append(("close", n))
    def branch_exists(self, b): return b in self.branches
    def delete_branch(self, b):
        self.log.append(("delete", b))
        if self.fail_delete:
            raise RuntimeError("deletion forbidden by a ruleset")
        self.branches.discard(b)
        return True
    def create_branch(self, b, from_branch="main"):
        self.branches.add(b)
        self.log.append(("branch", b, from_branch))
    def create_or_update_file(self, path, content, msg, branch):
        if self.fail_write:
            raise RuntimeError("write refused")
        self.files[(branch, path)] = content
        self.log.append(("write", branch))
    def open_pull_request(self, title, body, head, base):
        self.prs.append({"number": 99, "head_ref": head, "body": body})
        self.log.append(("pr", head, base))
        return "https://example/pr/99"


ORIGINAL = json.dumps(_inventory(), indent=2, ensure_ascii=False) + "\n"
TODAY = "2026-10-27"


def _change(new=None):
    return iu.build_update(_drift({"account": ["old_banner"]}, new), _inventory(), USED)


def _refresh(host, upd):
    return iu.open_or_refresh(host, upd, inventory_path=INV_PATH, original=ORIGINAL,
                              prefix=PREFIX, today=TODAY)


def _proposal(upd, number=7, branch=PREFIX + "2026-10-26", edit=None):
    """An open proposal as an earlier night left it (optionally edited)."""
    text = iu.dump_like(ORIGINAL, upd.inventory)
    body = iu.render_body(upd, INV_PATH, iu.content_hash(text))
    pr = {"number": number, "head_ref": branch, "body": body}
    return pr, {(branch, INV_PATH): edit(text) if edit else text}


def test_a_change_opens_one_pull_request_on_a_dated_branch_from_main():
    host = FakeHost()
    out = _refresh(host, _change())
    assert out == {"status": "opened", "url": "https://example/pr/99",
                   "branch": PREFIX + TODAY}
    assert host.log == [("branch", PREFIX + TODAY, "main"), ("write", PREFIX + TODAY),
                        ("pr", PREFIX + TODAY, "main")]
    text = host.files[(PREFIX + TODAY, INV_PATH)]
    assert "old_banner" not in json.loads(text)["pages"]["account"]["elements"]


def test_a_second_proposal_the_same_day_gets_its_own_branch():
    host = FakeHost()
    host.branches |= {PREFIX + TODAY, PREFIX + TODAY + "-2"}
    assert _refresh(host, _change())["branch"] == PREFIX + TODAY + "-3"


def test_no_change_and_no_pull_request_does_nothing():
    host = FakeHost()
    out = _refresh(host, iu.build_update(_drift({"account": []}), _inventory(), USED))
    assert out == {"status": "nothing_to_change"} and host.log == []


def test_the_same_proposal_again_leaves_the_open_pull_request_alone():
    pr, files = _proposal(_change())
    host = FakeHost([pr], files)
    assert _refresh(host, _change()) == {"status": "unchanged", "pr": 7} and host.log == []


def test_a_different_proposal_closes_the_untouched_one_and_opens_a_fresh_one():
    pr, files = _proposal(_change())
    host = FakeHost([pr], files)
    out = _refresh(host, _change({"account": {"phone_input": "#phone"}}))
    assert out["status"] == "opened" and out["branch"] == PREFIX + TODAY
    assert [e[0] for e in host.log] == ["comment", "close", "delete", "branch", "write", "pr"]
    assert "a fresh pull request replaces this one" in host.comments[7][0]


def test_nothing_to_change_closes_the_untouched_proposal():
    pr, files = _proposal(_change())
    host = FakeHost([pr], files)
    out = _refresh(host, iu.build_update(_drift({"account": []}), _inventory(), USED))
    assert out == {"status": "closed"}
    assert [e[0] for e in host.log] == ["comment", "close", "delete"]
    assert "needs no change now" in host.comments[7][0]


def test_a_branch_that_cannot_be_deleted_does_not_stop_the_new_proposal():
    pr, files = _proposal(_change())
    host = FakeHost([pr], files)
    host.fail_delete = True
    out = _refresh(host, _change({"account": {"phone_input": "#phone"}}))
    assert out["status"] == "opened" and ("close", 7) in host.log
    assert out["branch"] == PREFIX + TODAY, "a new dated branch: the old one may stay"


def test_a_proposal_a_person_edited_is_never_replaced_and_noted_once():
    pr, files = _proposal(_change(), edit=lambda t: t.replace("Save", "Store"))
    host = FakeHost([pr], files)
    other = _change({"account": {"phone_input": "#phone"}})
    assert _refresh(host, other) == {"status": "kept_edited", "prs": [7]}
    assert _refresh(host, other) == {"status": "kept_edited", "prs": [7]}
    assert [e[0] for e in host.log] == ["comment"], "one note per finding, no second PR"
    assert "edited by a person" in host.comments[7][0]


def test_a_pull_request_without_the_marker_on_the_prefix_is_a_persons():
    host = FakeHost([{"number": 5, "head_ref": PREFIX + "manual", "body": "my own fix"}],
                    {(PREFIX + "manual", INV_PATH): ORIGINAL})
    assert _refresh(host, _change())["status"] == "kept_edited"
    assert ("close", 5) not in host.log


def test_two_identical_open_proposals_are_reduced_to_one():
    a, fa = _proposal(_change(), number=7)
    b, fb = _proposal(_change(), number=8, branch=PREFIX + "2026-10-26-2")
    host = FakeHost([a, b], {**fa, **fb})
    assert _refresh(host, _change()) == {"status": "unchanged", "pr": 7}
    assert ("close", 8) in host.log and ("close", 7) not in host.log
    assert "identical proposal is already open" in host.comments[8][0]


def test_a_failed_write_leaves_no_half_written_branch():
    host = FakeHost()
    host.fail_write = True
    with pytest.raises(RuntimeError):
        _refresh(host, _change())
    assert host.log[-1] == ("delete", PREFIX + TODAY)


# ── the script ──────────────────────────────────────────────────────────

@pytest.fixture
def script_env(tmp_path, monkeypatch):
    from scripts import propose_inventory_update as script
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / INV_PATH).write_text(ORIGINAL, encoding="utf-8")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "p.py").write_text("X = ['save_button', 'email_input']\n")
    monkeypatch.setattr(script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(script.AppContext, "load",
                        classmethod(lambda cls: type("C", (), {"inventory_file": INV_PATH})()))
    state = {"settings": {"shadow_mode": False, "uncovered_max_age_hours": 48,
                          "inventory_update": {}},
             "host": None}
    monkeypatch.setattr(script, "impact_settings", lambda: state["settings"])
    monkeypatch.setattr(script, "_host", lambda: state["host"])

    def run(drift, *flags):
        report = tmp_path / "drift.json"
        report.write_text(json.dumps(drift))
        return script.main(["--drift-report", str(report), *flags])
    return run, state


def _fresh(**kw):
    return _drift({"account": ["old_banner"]}, checked_at=datetime.now(timezone.utc).isoformat(),
                  **kw)


def test_a_crawl_that_measured_nothing_proposes_and_closes_nothing(script_env, capsys):
    run, state = script_env
    state["host"] = FakeHost()
    assert run({"pages_checked": 0, "pages": {}}) == 0
    assert "measured no page" in capsys.readouterr().out and state["host"].log == []


def test_an_old_report_proposes_and_closes_nothing(script_env, capsys):
    run, state = script_env
    state["host"] = FakeHost()
    assert run(_drift({"account": ["old_banner"]}, checked_at="2020-01-01T00:00:00+00:00")) == 0
    assert "Drift report refused" in capsys.readouterr().out and state["host"].log == []


def test_a_dry_run_without_a_host_prints_and_removes_nothing(script_env, capsys):
    run, state = script_env
    assert run(_fresh(), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "--dry-run: nothing written" in out and "removed 0" in out
    assert "open pull requests could not be checked" in out


def test_shadow_mode_prints_and_never_writes(script_env, capsys):
    run, state = script_env
    state["settings"]["shadow_mode"] = True
    state["host"] = FakeHost()
    assert run(_fresh()) == 0
    assert "Agent 0 shadow mode: nothing written" in capsys.readouterr().out
    assert state["host"].log == []


def test_a_live_run_without_a_host_fails_and_writes_nothing(script_env, capsys):
    run, state = script_env
    assert run(_fresh()) == 1
    assert "Repository host unavailable" in capsys.readouterr().out


def test_a_live_run_opens_the_proposal_and_respects_keys_in_flight(script_env, capsys):
    run, state = script_env

    class Host(FakeHost):
        def list_open_prs(self, prefix="", strict=False):
            story = [{"number": 3, "head_ref": "auto/S-3-x", "body": ""}]
            return super().list_open_prs(prefix, strict) + ([] if prefix else story)
        def get_pr_changed_files(self, n):
            return [{"filename": "pages/p.py", "patch": "+k = 'saved_message'"}]

    state["host"] = Host()
    drift = _fresh()                                    # old_banner stale, no code names it
    drift["pages"]["account"]["missing"].append(
        {"element": "saved_message", "selector": "text=Saved"})   # named only by PR #3
    assert run(drift) == 0
    assert "'status': 'opened'" in capsys.readouterr().out
    written = json.loads(next(v for (b, p), v in state["host"].files.items() if p == INV_PATH))
    elements = written["pages"]["account"]["elements"]
    assert "old_banner" not in elements, "unused everywhere: removed"
    assert "saved_message" in elements, "an open story PR names it: kept"


# ── the workflow, the config and the host protocol ──────────────────────

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
    assert block == iu.DEFAULTS
    assert iu.settings(block)["branch_prefix"] == "inventory-update/"


def test_closing_a_pull_request_is_a_classified_repo_host_write():
    from core.dry_run import REPO_HOST_WRITES
    from integrations.repo_host import RepoHost
    assert hasattr(RepoHost, "close_pull_request") and "close_pull_request" in REPO_HOST_WRITES


def test_the_github_adapter_raises_a_listing_failure_only_when_strict():
    """The default stays best-effort for the sweeper and Agent 3; the inventory
    update asks for strict, or 'could not read' would look like 'none open'."""
    from unittest.mock import MagicMock
    from integrations.github_client import GitHubClient
    client = GitHubClient.__new__(GitHubClient)
    client._repo = MagicMock()
    client._repo.get_pulls.side_effect = RuntimeError("API down")
    assert client.list_open_prs() == []
    with pytest.raises(RuntimeError):
        client.list_open_prs(strict=True)


def test_an_unreadable_proposal_list_opens_no_duplicate():
    class Down(FakeHost):
        def list_open_prs(self, prefix="", strict=False):
            raise RuntimeError("API down")
    host = Down()
    with pytest.raises(RuntimeError):
        _refresh(host, _change())
    assert host.log == [], "nothing created while the open proposals are unknown"
