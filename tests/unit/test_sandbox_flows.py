"""
Sandbox flow tests: Phases A and B end to end, with dummy data, offline.

The REAL JiraClient runs against tests/sandbox/fake_jira.FakeJira, seeded by
tests/sandbox/seed.py (project SBX); the real scripts and agent code run
against a copy of this repository. Nothing touches a live Jira or GitHub.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.agent2_coder import (build_marker_index, compute_description_hash,
                                 parse_feature_file)
from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
from tests.sandbox.seed import DESCRIPTIONS, build_repo, repo_files, seed_jira


@pytest.fixture
def fake():
    return seed_jira()


@pytest.fixture
def jira(fake, monkeypatch):
    return jira_client_over(fake, monkeypatch)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = build_repo(tmp_path / "repo")
    import config.paths as paths
    import agents.agent2_coder as a2
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(paths, "PROJECT_ROOT", root)
    monkeypatch.setattr(a2, "FEATURES_DIR", root / "features")
    return root


@pytest.fixture
def tracker(jira, monkeypatch):
    """Every get_tracker() in the code under test returns the sandbox client."""
    import integrations.tracker as tr
    monkeypatch.setattr(tr, "get_tracker", lambda *a, **k: jira)
    return jira


def _keys(cases):
    return sorted(c["key"] for c in cases)


# ═════════════════════════════════════════════════════════════════
# Phase A
# ═════════════════════════════════════════════════════════════════
class TestA4TypedLinks:
    def test_owned_and_impacted_are_kept_apart(self, jira):
        assert _keys(jira.get_linked_test_cases("SBX-1")) == ["SBX-11", "SBX-12", "SBX-13"]
        assert _keys(jira.get_linked_test_cases("SBX-3")) == []      # owns nothing yet
        assert _keys(jira.get_impacted_test_cases("SBX-3")) == ["SBX-12"]
        assert jira.count_linked_test_cases("SBX-3") == 0          # Agent 1's guard passes

    def test_the_story_to_story_trace_is_not_a_test_case(self, jira, fake):
        assert "SBX-1" in fake.linked("SBX-3", "impacts")
        assert "SBX-1" not in _keys(jira.get_impacted_test_cases("SBX-3"))

    def test_retired_test_cases_are_invisible(self, jira):
        assert "SBX-33" not in _keys(jira.get_linked_test_cases("SBX-4"))
        assert jira.count_linked_test_cases("SBX-4") == 2

    def test_impacts_link_round_trip_with_idempotence(self, jira, fake):
        jira.link_issues("SBX-2", "SBX-11", "impacts")
        jira.link_issues("SBX-2", "SBX-11", "impacts")            # no second link
        assert sum(1 for t, i, o in fake.links.values()
                   if (t, i, o) == ("Impacts", "SBX-2", "SBX-11")) == 1
        assert _keys(jira.get_impacted_test_cases("SBX-2")) == ["SBX-11"]
        assert _keys(jira.get_linked_test_cases("SBX-2")) == ["SBX-21"]   # ownership unchanged
        jira.unlink_issues("SBX-2", "SBX-11", "impacts")
        assert jira.get_impacted_test_cases("SBX-2") == []
        assert jira.get_parent_story_key("SBX-11") == "SBX-1"

    def test_owns_link_matches_agent1s_layout(self, jira, fake):
        from core.schemas import TestCase, TestStep
        tc = TestCase(title="New case", description="d", priority="High", test_type="Positive",
                      preconditions=[], steps=[TestStep(step_number=1, action="a",
                                                        expected_result="e")],
                      expected_outcome="o", test_data=None)
        key = jira.create_test_case(tc, parent_story_key="SBX-3").key
        assert ("Relates", key, "SBX-3") in fake.links.values()   # test inward, story outward
        assert _keys(jira.get_linked_test_cases("SBX-3")) == [key]
        assert jira.get_parent_story_key(key) == "SBX-3"

    def test_update_test_case_keeps_the_hash_comparable(self, jira, fake):
        from core.schemas import TestCase, TestStep
        tc = TestCase(title="Login fails with an incorrect password", description="v2",
                      priority="High", test_type="Negative", preconditions=[],
                      steps=[TestStep(step_number=1, action="a", expected_result="e")],
                      expected_outcome="o", test_data=None)
        jira.update_test_case("SBX-12", tc)
        stored = fake.issues["SBX-12"]
        assert stored["summary"] == "[Negative] Login fails with an incorrect password"
        assert stored["description"] == jira._format_test_case_description(tc)
        assert _keys(jira.get_impacted_test_cases("SBX-3")) == ["SBX-12"]   # links untouched

    def test_create_story_for_drift(self, jira, fake):
        key = jira.create_story("Drift: login page", "inventory changed", ["Login"], ["impact-check"])
        assert fake.issues[key]["issuetype"] == "Story"
        assert fake.issues[key]["components"] == ["Login"]


class TestA5ParentLookup:
    def test_owner_wins_over_an_earlier_impacts_link(self, jira, fake):
        # SBX-12 carries Impacts from SBX-3 AND Relates to SBX-1
        assert jira.get_parent_story_key("SBX-12") == "SBX-1"

    def test_live_link_test_passes_against_the_sandbox(self, fake, monkeypatch):
        """The opt-in live test, run here against the simulator."""
        import integrations.jira_client as jc_mod
        import tests.integration.test_jira_links_live as live
        monkeypatch.setenv("LIVE_STORY_KEY", "SBX-2")
        monkeypatch.setenv("LIVE_TEST_CASE_KEY", "SBX-11")
        for var, val in (("JIRA_URL", "https://sandbox.invalid"), ("JIRA_EMAIL", "x"),
                         ("JIRA_API_TOKEN", "x"), ("JIRA_PROJECT_KEY", "SBX")):
            monkeypatch.setenv(var, val)
        monkeypatch.setattr(jc_mod.JiraClient, "client", property(lambda self: fake))
        live.test_impacts_link_reads_from_the_story_side()
        assert not any(t == "Impacts" and i == "SBX-2" for t, i, _o in fake.links.values())


class TestA2A3AgentTwoUpdate:
    """Agent 2's ai-update run on SBX-1: marker index finds the file, the
    modified case is spliced with its tags kept, nothing else moves."""

    def _run_update(self, repo, tracker, story="SBX-1"):
        import agents.agent2_coder as a2
        gh = FakeRepoHost(repo_files(repo))

        def one_scenario(llm, path, tc, ctx, existing):
            from agents.agent2_coder import format_marker
            return (f"  {format_marker(tc['key'], tc.get('description', ''))}\n"
                    f"  Scenario: {tc['summary'].split('] ')[-1]} (revised)\n"
                    f"    Then the revised step for {tc['key']}\n")

        with patch.object(a2, "get_tracker", return_value=tracker), \
             patch.object(a2, "get_repo_host", return_value=gh), \
             patch.object(a2, "LLMClient"), \
             patch.object(a2, "_generate_single_scenario", side_effect=one_scenario), \
             patch.object(a2, "_splice_step_defs_incremental",
                          side_effect=lambda *a, **k: ("# step defs", "spliced")), \
             patch.object(a2, "_validate_generated_files"):
            result = a2.run_update(story)
        return result, gh

    def test_modified_case_is_spliced_in_place_with_its_tags(self, repo, tracker, fake):
        fake.issues["SBX-12"]["description"] = "Wrong password now shows a clearer message."
        result, gh = self._run_update(repo, tracker)
        assert result["status"] in ("pr_opened", "updated") or gh.prs, result
        branch = gh.prs[0]["head_ref"]
        assert branch.startswith("auto/SBX-1-")
        new = gh.branches[branch]["features/sandbox_login.feature"]
        _h, blocks = parse_feature_file(new)
        by_key = {b.jira_key: b for b in blocks if b.jira_key}
        assert "(revised)" in by_key["SBX-12"].text()
        assert "@negative" in by_key["SBX-12"].text()                  # A2: tag kept
        assert "@smoke" in by_key["SBX-11"].text()                     # neighbour intact
        assert by_key["SBX-12"].jira_hash == compute_description_hash(
            "Wrong password now shows a clearer message.")
        assert "features/login.feature" not in [p for p in gh.branches[branch]
                                                if gh.branches[branch][p] != gh.branches["main"].get(p)]

    def test_an_unmarked_scenario_is_not_appended_twice(self, repo, tracker, fake):
        """SBX-13's scenario exists but has no marker yet. The update must not
        append a second copy of it (A3: legacy title match = skip and report)."""
        fake.issues["SBX-12"]["description"] = "changed"
        _result, gh = self._run_update(repo, tracker)
        new = gh.branches[gh.prs[0]["head_ref"]]["features/sandbox_login.feature"]
        assert new.count("Login fails with an unknown email address") == 1


# ═════════════════════════════════════════════════════════════════
# Phase B
# ═════════════════════════════════════════════════════════════════
class TestB2ImpactGraph:
    def test_the_sandbox_repository_builds_without_gaps(self, repo):
        from core.impact_graph import build_impact_graph
        g = build_impact_graph(repo)
        assert g.gaps == []
        assert g.stats()["scenarios"] == 8 and g.stats()["marked_scenarios"] == 2

    def test_an_element_change_finds_exactly_the_scenarios_that_use_it(self, repo):
        """An element SBX-12 uses and SBX-11 does not (taken from the graph, so
        no application name is written here): a change to it finds SBX-12, the
        unmarked twin scenario, and not SBX-11."""
        from core.impact_graph import build_impact_graph
        g = build_impact_graph(repo)
        only_12 = g.scenario_for_key("SBX-12").elements - g.scenario_for_key("SBX-11").elements
        assert only_12
        page, key = sorted(only_12)[0]
        hit = {s.ref for s in g.scenarios_using_element(page, key)}
        assert "SBX-12" in hit and "SBX-11" not in hit
        assert "features/sandbox_login.feature::Login fails with an unknown email address" in hit

    def test_story_components_reach_the_scenarios(self, repo, jira):
        from core.impact_graph import build_impact_graph
        g = build_impact_graph(repo)
        comps = jira.get_story("SBX-3")["components"]                # ["Login"]
        refs = {s.ref for c in comps for s in g.scenarios_in_component(c)}
        assert {"SBX-11", "SBX-12"} <= refs and len(refs) == 8


class TestB1Backfill:
    def _propose(self, repo, *extra):
        import scripts.backfill_markers as bf
        assert bf.main(["propose", "--out", "reports/p.json", *extra]) == 0
        return repo / "reports" / "p.json", json.loads((repo / "reports" / "p.json").read_text())

    def test_propose_on_the_real_reference_file_preselects_nothing(self, repo, tracker):
        _p, data = self._propose(repo)
        ref = [r for r in data["proposals"] if r["file"] == "login.feature"]
        assert len(ref) == 5
        assert not any(r["apply"] for r in ref)
        assert all("reserved" in r["note"] for r in ref)

    def test_old_app_look_alikes_are_why_a_person_confirms(self, repo, tracker):
        _p, data = self._propose(repo)
        ref = {r["scenario"]: r for r in data["proposals"] if r["file"] == "login.feature"}
        # The real reference title pairs with a look-alike from another application.
        assert ref["Successful login with valid credentials"]["owner"] == "SBX-4"

    def test_retired_cases_are_never_proposed(self, repo, tracker):
        _p, data = self._propose(repo)
        assert "SBX-33" not in {r["test_case"] for r in data["proposals"]}

    def test_story_filter_pairs_the_sandbox_scenario_with_its_own_case(self, repo, tracker):
        _p, data = self._propose(repo, "--story", "SBX-1")
        row = next(r for r in data["proposals"] if r["file"] == "sandbox_login.feature")
        assert row["test_case"] == "SBX-13" and row["apply"] is True

    def test_apply_marks_it_and_a_second_propose_finds_nothing_new(self, repo, tracker):
        import scripts.backfill_markers as bf
        path, data = self._propose(repo, "--story", "SBX-1")
        assert bf.main(["apply", str(path), "--yes"]) == 0
        index = build_marker_index(repo / "features")
        assert index.by_key["SBX-13"].hash == compute_description_hash(DESCRIPTIONS["SBX-13"])
        assert index.by_key["SBX-13"].file == "sandbox_login.feature"
        assert "SBX-1" not in json.dumps([r for r in self._propose(repo, "--story", "SBX-1")[1]
                                          ["proposals"] if r["file"] == "sandbox_login.feature"])
        assert (repo / "features" / "login.feature").read_text() == \
            (Path(__file__).resolve().parents[2] / "features" / "login.feature").read_text()

    def test_apply_open_pr_goes_through_the_repo_host(self, repo, tracker, monkeypatch):
        import scripts.backfill_markers as bf
        import integrations.repo_host as rh
        gh = FakeRepoHost(repo_files(repo))
        monkeypatch.setattr(rh, "get_repo_host", lambda *a, **k: gh)
        path, _ = self._propose(repo, "--story", "SBX-1")
        before = (repo / "features" / "sandbox_login.feature").read_text()
        assert bf.main(["apply", str(path), "--yes", "--open-pr"]) == 0
        assert len(gh.prs) == 1 and gh.prs[0]["head_ref"].startswith("chore/marker-backfill-")
        assert "# JIRA: SBX-13" in gh.branches[gh.prs[0]["head_ref"]]["features/sandbox_login.feature"]
        assert (repo / "features" / "sandbox_login.feature").read_text() == before

    def test_retiring_old_app_cases_removes_them_from_proposals(self, repo, tracker, fake):
        """What labelling the old-application test cases ai-retired would do."""
        for key in ("SBX-31", "SBX-32"):
            tracker.add_label(key, "ai-retired")
        _p, data = self._propose(repo)
        assert not {"SBX-31", "SBX-32"} & {r["test_case"] for r in data["proposals"]}


# ═════════════════════════════════════════════════════════════════
# Merge -> Done (PR #128)
# ═════════════════════════════════════════════════════════════════
class TestStoryDoneOnMerge:
    def _close(self, monkeypatch, *argv):
        import scripts.close_merged_story as cms
        monkeypatch.setattr("sys.argv", ["close_merged_story", *argv])
        return cms.main()

    def test_merged_story_branch_moves_the_card(self, tracker, fake, monkeypatch):
        import scripts.close_merged_story as cms
        monkeypatch.setattr(cms, "get_tracker", lambda *a, **k: tracker)
        assert self._close(monkeypatch, "--branch", "auto/SBX-2-shopping", "--merged", "true") == 0
        assert fake.issues["SBX-2"]["status"] == "Done"

    def test_framework_branch_is_skipped_and_moves_nothing(self, tracker, fake, monkeypatch):
        import scripts.close_merged_story as cms
        monkeypatch.setattr(cms, "get_tracker", lambda *a, **k: tracker)
        before = {k: v["status"] for k, v in fake.issues.items()}
        assert self._close(monkeypatch, "--branch", "feature/agent0-phase-c", "--merged", "true") == 0
        assert {k: v["status"] for k, v in fake.issues.items()} == before

    def test_rejected_pr_moves_nothing(self, tracker, fake, monkeypatch):
        assert self._close(monkeypatch, "--branch", "auto/SBX-2-shopping", "--merged", "false") == 0
        assert fake.issues["SBX-2"]["status"] == "In Review"
