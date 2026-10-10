"""
Unit tests for scripts/backfill_markers.py (Agent 0 design, step B1).

The backfill proposes a test case for every unmarked scenario, and writes
markers only for rows a person confirmed - re-checking each row first.
"""
import json
from unittest.mock import MagicMock

import pytest

import scripts.backfill_markers as bf
from agents.agent2_coder import (build_marker_index, compute_description_hash,
                                 greedy_title_pairing, parse_feature_file)

FEATURE = (
    "Feature: Login\n"
    "\n"
    "  Background:\n"
    "    Given I am on the login page\n"
    "\n"
    "  @smoke\n"
    "  Scenario: Successful login with valid credentials\n"
    "    When I log in\n"
    "    Then I am logged in\n"
    "\n"
    "  # JIRA: AB-9 (hash: 99999999)\n"
    "  Scenario: Already marked\n"
    "    Then fine\n"
    "\n"
    "  Scenario: Login fails with an incorrect password\n"
    "    When I log in wrongly\n"
    "    Then I see an error\n"
)

CASES = [
    {"key": "AB-1", "summary": "[Positive] Successful login with valid credentials",
     "description": "desc one", "owner": "AB-100"},
    {"key": "AB-2", "summary": "[Negative] [Negative] Login fails with incorrect password",
     "description": "desc two", "owner": "AB-100"},
    {"key": "AB-3", "summary": "[Edge] Something about the cart", "description": "x",
     "owner": "AB-200"},
    {"key": "AB-9", "summary": "Already marked", "description": "y", "owner": "AB-100"},
]


def _titles(content):
    _h, blocks = parse_feature_file(content)
    return {b.jira_key: b for b in blocks if b.kind == "scenario"}


class TestGreedyPairing:
    def test_best_match_first_each_case_once(self):
        chosen, claimed = greedy_title_pairing(
            {"a": "login works", "b": "cart works"},
            [{"summary": "cart works"}, {"summary": "login works"}])
        assert chosen["a"][1]["summary"] == "login works"
        assert chosen["b"][1]["summary"] == "cart works"
        assert claimed == {0, 1}


class TestBuildProposals:
    UNMARKED = [("login.feature", "Successful login with valid credentials"),
                ("login.feature", "Login fails with an incorrect password")]

    def test_pairs_by_title_with_type_tags_ignored(self):
        rows = bf.build_proposals(self.UNMARKED, CASES, {"AB-9"}, set())
        assert [(r["test_case"], r["apply"]) for r in rows] == [("AB-1", True), ("AB-2", True)]
        assert rows[0]["owner"] == "AB-100" and rows[0]["score"] == 1.0

    def test_marked_keys_are_never_proposed(self):
        rows = bf.build_proposals([("f.feature", "Already marked")], CASES, {"AB-9"}, set())
        assert rows[0]["test_case"] != "AB-9"

    def test_below_floor_is_proposed_but_not_applied(self):
        rows = bf.build_proposals([("f.feature", "Totally unrelated words")], CASES[2:3], set(), set())
        assert rows[0]["test_case"] == "AB-3" and rows[0]["apply"] is False
        assert "below the floor" in rows[0]["note"]

    def test_no_candidates(self):
        rows = bf.build_proposals(self.UNMARKED, [], set(), set())
        assert all(r["test_case"] is None and not r["apply"] for r in rows)

    def test_reserved_file_is_never_preselected(self):
        rows = bf.build_proposals(self.UNMARKED, CASES, set(), {"login.feature"})
        assert all(not r["apply"] and "reserved" in r["note"] for r in rows)


class TestInsertMarkers:
    def test_marker_goes_below_tags_with_the_scenarios_indent(self):
        out, status = bf.insert_markers(FEATURE, {
            "Successful login with valid credentials": ("AB-1", "desc one")})
        assert status == {"Successful login with valid credentials": "applied"}
        assert ("  @smoke\n  # JIRA: AB-1 (hash: "
                f"{compute_description_hash('desc one')})\n"
                "  Scenario: Successful login with valid credentials\n") in out

    def test_only_the_marker_line_is_added(self):
        out, _ = bf.insert_markers(FEATURE, {
            "Login fails with an incorrect password": ("AB-2", "desc two")})
        added = [l for l in out.splitlines() if l not in FEATURE.splitlines()]
        assert len(added) == 1 and added[0].strip().startswith("# JIRA: AB-2")
        assert len(out.splitlines()) == len(FEATURE.splitlines()) + 1

    def test_marked_scenario_parses_with_its_key_and_hash(self, tmp_path):
        out, _ = bf.insert_markers(FEATURE, {
            "Successful login with valid credentials": ("AB-1", "desc one"),
            "Login fails with an incorrect password": ("AB-2", "desc two")})
        (tmp_path / "login.feature").write_text(out)
        index = build_marker_index(tmp_path)
        assert index.by_key["AB-1"].hash == compute_description_hash("desc one")
        assert index.by_key["AB-2"].title == "Login fails with an incorrect password"
        assert "@smoke" in _titles(out)["AB-1"].text()

    def test_already_marked_missing_and_ambiguous_are_skipped(self):
        dup = FEATURE + "\n  Scenario: Login fails with an incorrect password\n    Then again\n"
        out, status = bf.insert_markers(dup, {
            "Already marked": ("AB-5", "d"),
            "No such scenario": ("AB-6", "d"),
            "Login fails with an incorrect password": ("AB-7", "d")})
        assert status["Already marked"] == "already marked AB-9"
        assert status["No such scenario"] == "scenario not found"
        assert "not unique" in status["Login fails with an incorrect password"]
        assert out == dup


class TestValidateRows:
    def _row(self, key, file="login.feature", apply=True, scenario="s"):
        return {"file": file, "scenario": scenario, "test_case": key, "apply": apply}

    def test_reasons(self):
        live = {"AB-1": {}, "AB-2": {}, "AB-4": {}}
        rows = [self._row("AB-1"), self._row("AB-1", scenario="t"), self._row("AB-9"),
                self._row("AB-3"), self._row(None), self._row("AB-2", apply=False),
                self._row("AB-4", file="ref.feature")]
        accepted, rejected = bf.validate_rows(rows, {"AB-9"}, live, {"ref.feature"}, False)
        assert [r["test_case"] for r in accepted] == ["AB-1"]
        reasons = [why for _r, why in rejected]
        assert any("more than one scenario" in r for r in reasons)
        assert any("already marked" in r for r in reasons)
        assert any("not a (non-retired) test case" in r for r in reasons)
        assert any("no test case given" in r for r in reasons)
        assert any("reserved" in r for r in reasons)
        assert len(rejected) == 5                      # the apply=false row is ignored

    def test_allow_reserved(self):
        accepted, _ = bf.validate_rows([self._row("AB-4", file="ref.feature")], set(),
                                       {"AB-4": {}}, {"ref.feature"}, True)
        assert len(accepted) == 1


# ─────────────────────────────────────────────────────────────────
# Commands, end to end with a fake tracker and repo host
# ─────────────────────────────────────────────────────────────────
@pytest.fixture
def project(tmp_path, monkeypatch):
    import config.paths as paths
    feats = tmp_path / "features"
    feats.mkdir()
    (feats / "login.feature").write_text(FEATURE)
    monkeypatch.setattr(paths, "FEATURES_DIR", feats)
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(bf, "_reserved_feature_files", lambda: set())
    tracker = MagicMock()
    tracker.get_all_test_cases.return_value = CASES
    import integrations.tracker as tr
    monkeypatch.setattr(tr, "get_tracker", lambda *a, **k: tracker)
    return tmp_path


def _propose(project, *extra):
    assert bf.main(["propose", "--out", "reports/p.json", *extra]) == 0
    return project / "reports" / "p.json"


class TestCommands:
    def test_propose_writes_proposals_and_changes_no_feature(self, project):
        path = _propose(project)
        data = json.loads(path.read_text())
        assert [r["test_case"] for r in data["proposals"]] == ["AB-1", "AB-2"]
        assert (project / "features" / "login.feature").read_text() == FEATURE

    def test_story_filter_limits_candidates(self, project):
        data = json.loads(_propose(project, "--story", "AB-200").read_text())
        assert data["candidates"] == 1
        assert {r["test_case"] for r in data["proposals"]} <= {"AB-3", None}

    def test_apply_writes_local_files(self, project):
        path = _propose(project)
        assert bf.main(["apply", str(path), "--yes"]) == 0
        index = build_marker_index(project / "features")
        assert set(index.by_key) == {"AB-1", "AB-2", "AB-9"}
        assert index.by_key["AB-2"].hash == compute_description_hash("desc two")

    def test_apply_respects_unconfirmed_rows(self, project):
        path = _propose(project)
        data = json.loads(path.read_text())
        data["proposals"][1]["apply"] = False
        path.write_text(json.dumps(data))
        bf.main(["apply", str(path), "--yes"])
        assert set(build_marker_index(project / "features").by_key) == {"AB-1", "AB-9"}

    def test_apply_twice_is_harmless(self, project):
        path = _propose(project)
        bf.main(["apply", str(path), "--yes"])
        once = (project / "features" / "login.feature").read_text()
        assert bf.main(["apply", str(path), "--yes"]) == 1      # all rows now rejected
        assert (project / "features" / "login.feature").read_text() == once

    def test_apply_without_yes_needs_typed_confirmation(self, project, monkeypatch):
        path = _propose(project)
        monkeypatch.setattr("builtins.input", lambda _p: "no")
        assert bf.main(["apply", str(path)]) == 1
        assert (project / "features" / "login.feature").read_text() == FEATURE

    def test_apply_open_pr_uses_main_and_leaves_local_files(self, project, monkeypatch):
        path = _propose(project)
        gh = MagicMock()
        gh.get_file_content.return_value = FEATURE
        gh.open_pull_request.return_value = "https://example/pull/9"
        import integrations.repo_host as rh
        monkeypatch.setattr(rh, "get_repo_host", lambda *a, **k: gh)
        assert bf.main(["apply", str(path), "--yes", "--open-pr"]) == 0
        branch = gh.create_branch.call_args.args[0]
        assert branch.startswith("chore/marker-backfill-")
        gh.get_file_content.assert_called_once_with("features/login.feature", branch="main")
        rel, content, _msg, used_branch = gh.create_or_update_file.call_args.args
        assert rel == "features/login.feature" and used_branch == branch
        assert "# JIRA: AB-1" in content and "# JIRA: AB-2" in content
        gh.open_pull_request.assert_called_once()
        assert (project / "features" / "login.feature").read_text() == FEATURE
