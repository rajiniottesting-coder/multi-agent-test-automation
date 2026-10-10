"""
Unit tests for the marker index (Agent 0 design, step A3).

Agent 2 decides what to generate by test case identity - the key in the
`# JIRA:` marker - and falls back to the title only for unmarked legacy
scenarios. Before, it matched titles only, so a revised test case (same
title, new description) was skipped as "already covered" and a renamed
one was generated a second time.
"""

from pathlib import Path

import pytest

from agents import agent2_coder
from agents.agent2_coder import (
    _locate_feature_file_for_story,
    _select_new_test_cases,
    build_marker_index,
    classify_against_index,
    format_marker,
)


def _write(dir_: Path, name: str, scenarios: list[tuple]) -> None:
    """scenarios: [(key or None, description, title)]"""
    parts = ["Feature: F\n"]
    for key, desc, title in scenarios:
        parts.append("\n")
        if key:
            parts.append(f"  {format_marker(key, desc)}\n")
        parts.append(f"  Scenario: {title}\n    Then it works\n")
    (dir_ / name).write_text("".join(parts), encoding="utf-8")


@pytest.fixture
def features(tmp_path):
    _write(tmp_path, "login.feature", [
        ("AB-1", "valid login steps", "Valid login"),
        ("AB-2", "wrong password steps", "Wrong password"),
        (None, "", "Legacy remember me"),
    ])
    _write(tmp_path, "cart.feature", [
        ("AB-7", "add to cart steps", "Add to cart"),
    ])
    return tmp_path


class TestBuildMarkerIndex:
    def test_indexes_every_marked_scenario_with_its_file(self, features):
        index = build_marker_index(features)
        assert set(index.by_key) == {"AB-1", "AB-2", "AB-7"}
        assert index.by_key["AB-1"].file == "login.feature"
        assert index.by_key["AB-7"].file == "cart.feature"
        assert index.by_key["AB-2"].title == "Wrong password"

    def test_lists_unmarked_scenarios(self, features):
        index = build_marker_index(features)
        assert index.unmarked == [("login.feature", "Legacy remember me")]

    def test_key_marked_twice_is_reported(self, features):
        _write(features, "zz_copy.feature", [("AB-1", "x", "Valid login copy")])
        index = build_marker_index(features)
        assert index.by_key["AB-1"].file == "login.feature"
        assert index.duplicates == {"AB-1": ["login.feature", "zz_copy.feature"]}

    def test_missing_directory_gives_empty_index(self, tmp_path):
        index = build_marker_index(tmp_path / "nope")
        assert index.by_key == {} and index.unmarked == []

    def test_files_for_keys_groups_by_file(self, features):
        index = build_marker_index(features)
        assert index.files_for_keys(["AB-7", "AB-1", "AB-99"]) == {
            "cart.feature": ["AB-7"], "login.feature": ["AB-1"],
        }


class TestClassifyAgainstIndex:
    def _classes(self, features, cases):
        out = classify_against_index(cases, build_marker_index(features))
        return {c: [i["test_case"]["key"] for i in items] for c, items in out.items()}

    def test_four_way_classification(self, features):
        cases = [
            {"key": "AB-1", "summary": "Valid login", "description": "valid login steps"},
            {"key": "AB-2", "summary": "Wrong password", "description": "REVISED steps"},
            {"key": "AB-5", "summary": "Legacy remember me", "description": "x"},
            {"key": "AB-6", "summary": "Brand new case", "description": "y"},
        ]
        assert self._classes(features, cases) == {
            "unchanged": ["AB-1"], "modified": ["AB-2"], "legacy": ["AB-5"],
            "title_clash": [], "new": ["AB-6"],
        }

    def test_revised_case_with_same_title_is_modified_not_covered(self, features):
        cases = [{"key": "AB-2", "summary": "Wrong password", "description": "v2"}]
        assert self._classes(features, cases)["modified"] == ["AB-2"]

    def test_renamed_case_keeps_its_identity(self, features):
        cases = [{"key": "AB-1", "summary": "Login with valid credentials",
                  "description": "valid login steps"}]
        assert self._classes(features, cases)["unchanged"] == ["AB-1"]

    def test_same_title_as_another_key_is_a_clash(self, features):
        cases = [{"key": "AB-9", "summary": "Valid login", "description": "z"}]
        out = classify_against_index(cases, build_marker_index(features))
        assert [i["other_key"] for i in out["title_clash"]] == ["AB-1"]
        assert out["new"] == []


class TestSelectNewTestCases:
    def test_only_new_cases_are_generated(self, features):
        cases = [
            {"key": "AB-1", "summary": "Valid login", "description": "valid login steps"},
            {"key": "AB-2", "summary": "Wrong password", "description": "v2"},
            {"key": "AB-6", "summary": "Brand new case", "description": "y"},
        ]
        new, skipped = _select_new_test_cases(cases, False, features)
        assert [c["key"] for c in new] == ["AB-6"]
        assert {s["test_case"]["key"]: s["reason"] for s in skipped} == {
            "AB-1": "unchanged", "AB-2": "modified",
        }
        assert all("matched_file" in s and "matched_scenario" in s for s in skipped)

    def test_regenerate_bypasses_dedup(self, features):
        cases = [{"key": "AB-1", "summary": "Valid login", "description": "x"}]
        new, skipped = _select_new_test_cases(cases, True, features)
        assert new == cases and skipped == []

    def test_defaults_to_project_features_dir(self, features, monkeypatch):
        monkeypatch.setattr(agent2_coder, "FEATURES_DIR", features)
        new, _ = _select_new_test_cases(
            [{"key": "AB-6", "summary": "Brand new case", "description": "y"}], False
        )
        assert [c["key"] for c in new] == ["AB-6"]


class TestLocateFeatureFile:
    def test_finds_the_file_that_holds_the_keys(self, features):
        index = build_marker_index(features)
        assert _locate_feature_file_for_story(
            "S-1", [{"key": "AB-7"}], index) == "features/cart.feature"

    def test_spread_keys_pick_the_file_with_most(self, features):
        index = build_marker_index(features)
        cases = [{"key": "AB-1"}, {"key": "AB-2"}, {"key": "AB-7"}]
        assert _locate_feature_file_for_story("S-1", cases, index) == "features/login.feature"

    def test_no_marked_key_returns_none(self, features):
        index = build_marker_index(features)
        assert _locate_feature_file_for_story("S-1", [{"key": "AB-99"}], index) is None

    def test_default_index_does_not_crash(self, features, monkeypatch):
        # Regression: the old implementation called scan_features_dir()
        # without its required argument and raised TypeError on every
        # ai-update run.
        monkeypatch.setattr(agent2_coder, "FEATURES_DIR", features)
        assert _locate_feature_file_for_story(
            "S-1", [{"key": "AB-1"}]) == "features/login.feature"
