"""Every auto-raised defect is LINKED to what its test verifies.

Before: a defect named its test case and owning story in its description text
only - neither showed the defect - and a test without a `# JIRA:` marker (all
five login reference tests, 30 Oct 2026) was "not marked", with nothing to say
which story it belonged to.

Now (core/defects.py, scripts/triage_failures.py):
  - "<defect> blocks <test case>" and "<defect> relates to <story>" (link
    kinds `defect_of` / `defect_story`, tracker.link_types);
  - the defect takes the story's components;
  - traced from the scenario's marker; else the one story the marked
    scenarios of its feature file share; else `defects.trace_owners` (files
    that must not carry markers, such as the reserved reference files); else
    NOT traced - `ai-defect-unmapped` and one `defects-unmapped` alert;
  - kept current on every update: missing links added (older defects
    included), a moved owner or test case moves its link, the label goes once
    traced; a trace to an issue that no longer exists is reported, not a
    refused write.

Sandbox: the real JiraClient over a fake Jira. Generic names only.
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from core import defects
from core import pipeline_health as ph
from scripts import triage_failures as tf
from tests.sandbox.fake_jira import FakeJira, jira_client_over

ROOT = Path(__file__).resolve().parents[2]
MSG = "AssertionError: total was 0"


def _junit(tmp_path, n, *names, module="test_cart"):
    d = tmp_path / f"run{n}"
    d.mkdir()
    cases = "".join(
        f'<testcase classname="tests.step_defs.{module}" name="{name}"><properties>'
        f'<property name="retried" value="1"/></properties>'
        f'<failure message="{MSG}">{MSG}</failure></testcase>' for name in names)
    (d / "junit.xml").write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
    return d / "junit.xml"


@pytest.fixture
def world(monkeypatch, tmp_path):
    ph.reset_cache()
    fake = FakeJira()
    fake.add("Story", "A shopper keeps a cart", key="SBX-101", components=["Cart"])
    fake.add("Story", "A shopper checks out", key="SBX-102", components=["Checkout"])
    fake.add("Test Case", "[Positive] Add an item", key="SBX-105")
    fake.add("Test Case", "[Positive] Add two items", key="SBX-106")
    jira = jira_client_over(fake, monkeypatch)
    features = tmp_path / "features"
    features.mkdir()
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-105 (hash: abc12345) owner: SBX-101\n"
        "  Scenario: Add an item\n    Given I am home\n\n"
        "  Scenario: Remove an item\n    Given I am home\n")
    (features / "reference.feature").write_text(
        "Feature: Reference\n\n  Scenario: Sign in\n    Given I am home\n")
    real = defects.section("defects")
    # The cap is the test's own: the shipped value is an operator's choice
    # (lowered to 1 for one validation night, it broke this suite).
    settings = {**real, "trace_owners": {}, "max_new_per_run": 10}
    monkeypatch.setattr(defects, "settings", lambda: settings)
    yield fake, jira, features, settings
    ph.reset_cache()


def _run(world, tmp_path, n, *names, module="test_cart", **kw):
    fake, jira, features, _ = world
    return tf.run(jira, _junit(tmp_path, n, *names, module=module),
                  f"https://ci.example/runs/{n}", features, **kw)


def _bug(fake):
    (key,) = [k for k, d in fake.issues.items() if d["issuetype"] == "Bug"]
    return key


def _links(fake, key):
    """{(type, other, reading)} for every link of `key`."""
    out = set()
    for t, inward, outward in fake.links.values():
        if inward == key:
            out.add((t, outward, "from"))
        elif outward == key:
            out.add((t, inward, "to"))
    return out


def _alerts(fake):
    key = next((k for k, d in fake.issues.items() if "pipeline-health" in d["labels"]), None)
    return [c.splitlines()[0] for c in fake.comments.get(key, [])] if key else []


# Keys well above the fake's own numbering, which a raised defect takes.

# ── traced by the scenario's marker ─────────────────────────────────────────

def test_a_marked_test_links_its_test_case_and_story_and_takes_the_components(world, tmp_path):
    fake, jira, *_ = world
    out = _run(world, tmp_path, 1, "test_add_an_item")
    key = _bug(fake)
    assert _links(fake, key) == {("Blocks", "SBX-105", "from"), ("Relates", "SBX-101", "from")}
    assert fake.issues[key]["components"] == ["Cart"]
    assert "ai-defect-unmapped" not in fake.issues[key]["labels"]
    state = defects.state_of(fake.issues[key]["description"])
    assert (state["test_case"], state["owner"], state["traced_by"]) == \
        ("SBX-105", "SBX-101", "scenario marker")
    assert out["unmapped"] == [] and out["errors"] == [] and out["stale_trace"] == []


def test_the_test_case_reads_is_blocked_by_and_the_story_finds_it(world, tmp_path):
    fake, jira, *_ = world
    _run(world, tmp_path, 1, "test_add_an_item")
    key = _bug(fake)
    tc = jira.client.issue("SBX-105")
    (link,) = [l for l in tc.fields.issuelinks if l.type.name == "Blocks"]
    assert link.inwardIssue.key == key and link.type.inward == "is blocked by"
    assert key in fake.linked("SBX-101", "relates to")


def test_the_story_still_owns_only_its_test_cases(world, tmp_path):
    """A defect "relates to" its story like a test case does; every test case
    query also names the issue type, so the defect never becomes one."""
    fake, jira, *_ = world
    fake.link("Relates", "SBX-105", "SBX-101")
    _run(world, tmp_path, 1, "test_add_an_item")
    assert [t["key"] for t in jira.get_linked_test_cases("SBX-101")] == ["SBX-105"]
    assert jira.get_parent_story_key("SBX-105") == "SBX-101"


# ── traced without a marker ─────────────────────────────────────────────────

def test_an_unmarked_scenario_is_traced_to_the_story_its_file_shares(world, tmp_path):
    fake, *_ = world
    _run(world, tmp_path, 1, "test_remove_an_item")
    key = _bug(fake)
    assert _links(fake, key) == {("Relates", "SBX-101", "from")}, "no test case to block"
    state = defects.state_of(fake.issues[key]["description"])
    assert (state["test_case"], state["owner"], state["traced_by"]) == \
        (None, "SBX-101", "feature file")
    assert "ai-defect-unmapped" not in fake.issues[key]["labels"]


def test_a_file_shared_by_two_stories_traces_no_unmarked_scenario(world, tmp_path):
    fake, _, features, _ = world
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-105 (hash: abc12345) owner: SBX-101\n"
        "  Scenario: Add an item\n    Given I am home\n\n"
        "  # JIRA: SBX-106 (hash: abc12346) owner: SBX-102\n"
        "  Scenario: Add two items\n    Given I am home\n\n"
        "  Scenario: Remove an item\n    Given I am home\n")
    out = _run(world, tmp_path, 1, "test_remove_an_item")
    key = _bug(fake)
    assert out["unmapped"] == [key] and _links(fake, key) == set()


@pytest.mark.parametrize("path", ["features/reference.feature", "reference.feature",
                                  "/features/reference.feature"])
def test_a_file_that_cannot_carry_markers_is_traced_by_configuration(world, tmp_path, path):
    fake, _, _, settings = world
    settings["trace_owners"] = {path: "sbx-102"}
    out = _run(world, tmp_path, 1, "test_sign_in", module="test_reference")
    key = _bug(fake)
    assert _links(fake, key) == {("Relates", "SBX-102", "from")}
    assert fake.issues[key]["components"] == ["Checkout"] and out["unmapped"] == []
    assert "defects.trace_owners" in fake.issues[key]["description"]


def test_an_untraced_defect_is_labelled_and_alerted_until_it_is_traced(world, tmp_path):
    fake, _, features, settings = world
    out = _run(world, tmp_path, 1, "test_sign_in", module="test_reference")
    key = _bug(fake)
    assert out["unmapped"] == [key] and "ai-defect-unmapped" in fake.issues[key]["labels"]
    assert "NOT TRACED" in fake.issues[key]["description"]
    assert f"[health:open] {tf.UNMAPPED}" in _alerts(fake)
    # a person adds a marker; the next failure links it and clears the label
    (features / "reference.feature").write_text(
        "Feature: Reference\n\n  # JIRA: SBX-106 (hash: abc12346) owner: SBX-102\n"
        "  Scenario: Sign in\n    Given I am home\n")
    out = _run(world, tmp_path, 2, "test_sign_in", module="test_reference")
    assert out["updated"] == [key] and out["unmapped"] == []
    assert _links(fake, key) == {("Blocks", "SBX-106", "from"), ("Relates", "SBX-102", "from")}
    assert "ai-defect-unmapped" not in fake.issues[key]["labels"]
    assert _alerts(fake)[-1] == f"[health:resolved] {tf.UNMAPPED}"


def test_two_untraced_defects_stay_two_defects(world, tmp_path):
    """The unmapped label shares the defect label's prefix; it must never be
    read as a defect's own label."""
    fake, *_ = world
    _run(world, tmp_path, 1, "test_sign_in", "test_sign_out", module="test_reference")
    out = _run(world, tmp_path, 2, "test_sign_in", "test_sign_out", module="test_reference")
    assert out["raised"] == [] and len(out["updated"]) == 2
    assert len([d for d in fake.issues.values() if d["issuetype"] == "Bug"]) == 2


def test_an_untraced_defect_passing_again_is_flagged_once(world, tmp_path):
    fake, jira, features, _ = world
    _run(world, tmp_path, 1, "test_sign_in", module="test_reference")
    key = _bug(fake)
    d = tmp_path / "run2"
    d.mkdir()
    (d / "junit.xml").write_text('<testsuites><testsuite><testcase classname='
                                 '"tests.step_defs.test_reference" name="test_sign_in"/>'
                                 '</testsuite></testsuites>')
    out = tf.run(jira, d / "junit.xml", "https://ci.example/runs/2", features)
    assert out["passing"] == [key]
    assert len([c for c in fake.comments[key] if "Suggest closing" in c]) == 1


# ── kept current ────────────────────────────────────────────────────────────

def test_a_repeat_adds_no_second_link(world, tmp_path):
    fake, *_ = world
    _run(world, tmp_path, 1, "test_add_an_item")
    _run(world, tmp_path, 2, "test_add_an_item")
    key = _bug(fake)
    assert len([l for l in fake.links.values() if key in l[1:]]) == 2


def test_a_moved_owner_and_test_case_move_their_links(world, tmp_path):
    fake, _, features, _ = world
    _run(world, tmp_path, 1, "test_add_an_item")
    key = _bug(fake)
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-106 (hash: abc12346) owner: SBX-102\n"
        "  Scenario: Add an item\n    Given I am home\n")
    _run(world, tmp_path, 2, "test_add_an_item")
    assert _links(fake, key) == {("Blocks", "SBX-106", "from"), ("Relates", "SBX-102", "from")}
    assert fake.issues[key]["components"] == ["Checkout"]


def test_a_defect_raised_before_traceability_is_linked_on_its_next_update(world, tmp_path):
    fake, *_ = world
    label = defects.defect_label("tests.step_defs.test_cart::test_add_an_item", "unclassified")
    old_state = {"test": "tests.step_defs.test_cart::test_add_an_item", "test_case": "SBX-105",
                 "owner": "SBX-101", "cause": "unclassified", "cause_text": "x", "remedy": "y",
                 "failure": MSG, "times": 3, "first_seen": "2026-10-01",
                 "last_seen": "2026-10-02", "last_run": "https://ci.example/runs/0"}
    old = fake.add("Bug", "[Auto] old", labels=["ai-defect", label],
                   description=defects.render(None, old_state))
    out = _run(world, tmp_path, 1, "test_add_an_item")
    assert out["raised"] == [] and out["updated"] == [old]
    assert _links(fake, old) == {("Blocks", "SBX-105", "from"), ("Relates", "SBX-101", "from")}
    assert defects.state_of(fake.issues[old]["description"])["times"] == 4
    assert label not in fake.issues[old]["labels"], "its fingerprint label goes on the update"


# ── what goes wrong ─────────────────────────────────────────────────────────

def test_a_trace_to_a_deleted_test_case_is_reported_not_a_refused_write(world, tmp_path):
    fake, _, features, _ = world
    (features / "cart.feature").write_text(
        "Feature: Cart\n\n  # JIRA: SBX-199 (hash: abc12345) owner: SBX-101\n"
        "  Scenario: Add an item\n    Given I am home\n")
    out = _run(world, tmp_path, 1, "test_add_an_item")
    key = _bug(fake)
    assert out["errors"] == [] and out["stale_trace"] == [f"{key} -> SBX-199"]
    assert _links(fake, key) == {("Relates", "SBX-101", "from")}, "the story is still linked"
    assert f"[health:open] {tf.UNMAPPED}" in _alerts(fake)
    assert f"[health:open] {tf.NOT_WRITTEN}" not in _alerts(fake)


def test_a_link_type_the_tracker_lacks_is_a_refused_write(world, tmp_path, monkeypatch):
    fake, jira, *_ = world
    types = dict(jira.link_types)
    types["defect_of"] = {**types["defect_of"], "name": "Causes"}
    monkeypatch.setattr(type(jira), "link_types", property(lambda self: types))
    out = _run(world, tmp_path, 1, "test_add_an_item")
    key = _bug(fake)
    assert [what for what, _ in out["errors"]] == [f"{key} link to SBX-105"]
    assert _links(fake, key) == {("Relates", "SBX-101", "from")}
    assert f"[health:open] {tf.NOT_WRITTEN}" in _alerts(fake)


def test_components_are_a_nicety_never_a_failure(world, tmp_path, monkeypatch):
    fake, jira, *_ = world

    def refuse(*a, **k):
        raise RuntimeError("Field 'components' cannot be set")
    monkeypatch.setattr(jira, "set_components", refuse)
    out = _run(world, tmp_path, 1, "test_add_an_item")
    assert out["errors"] == [] and len(_links(fake, _bug(fake))) == 2


def test_a_story_without_components_gives_none(world, tmp_path):
    fake, *_ = world
    fake.issues["SBX-101"]["components"] = []
    _run(world, tmp_path, 1, "test_add_an_item")
    assert fake.issues[_bug(fake)]["components"] == []


def test_a_tracker_without_the_capability_still_links(world, tmp_path, monkeypatch):
    fake, jira, *_ = world
    monkeypatch.setattr(type(jira), "set_components", None, raising=False)
    out = _run(world, tmp_path, 1, "test_add_an_item")
    assert out["errors"] == [] and len(_links(fake, _bug(fake))) == 2


def test_both_switches_turn_it_off(world, tmp_path):
    fake, _, _, settings = world
    settings.update(trace_links=False, copy_components=False)
    _run(world, tmp_path, 1, "test_add_an_item")
    key = _bug(fake)
    assert _links(fake, key) == set() and fake.issues[key]["components"] == []


def test_a_dry_run_writes_nothing_and_still_says_what_is_untraced(world, tmp_path):
    fake, *_ = world
    out = _run(world, tmp_path, 1, "test_sign_in", module="test_reference", dry_run=True)
    assert [d for d in fake.issues.values() if d["issuetype"] == "Bug"] == []
    assert fake.links == {} and out["unmapped"] and out["unmapped"][0].startswith("(dry run)")


# ── shipped settings ────────────────────────────────────────────────────────

def test_the_link_kinds_have_defaults_and_the_shipped_config_names_them():
    from integrations.tracker import _DEFAULT_LINK_TYPES, LINK_KINDS, tracker_settings
    assert {"defect_of", "defect_story"} <= set(LINK_KINDS) <= set(_DEFAULT_LINK_TYPES)
    types = tracker_settings()["link_types"]
    assert types["defect_of"]["name"] == "Blocks" and types["defect_story"]["name"] == "Relates"


def test_every_trace_owners_file_exists_and_carries_no_marker():
    """trace_owners is for files that cannot carry markers; a mapped file that
    gained markers would be traced twice, a missing one not at all."""
    cfg = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    owners = cfg["defects"]["trace_owners"]
    reserved = set((cfg.get("app_under_test") or {}).get("reserved_paths") or [])
    for path, story in owners.items():
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "# JIRA:" not in text, path
        assert path in reserved, f"{path}: map only files the agents cannot mark"
        assert story and "-" in story
