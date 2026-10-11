"""
Phase D (Agent 0 design): Agent 0 end to end in the sandbox.

D1 code-change and drift triggers (no model), D3 requirement trigger with
the short-list rule, D4 in-flight guard and delta re-analysis, D5 the live
loop (review -> hand-over -> reconcile -> outcome), and the safety switches.
The model is a fake that answers from the prompts Agent 0 builds. No
application name is written here: elements are taken from the graph.
"""
import json
import re
import shutil
from unittest.mock import MagicMock

import pytest

import agents.agent0_impact as a0
from core import impact_analysis as ia
from core.impact_graph import build_impact_graph
from core.impact_reconcile import reconcile_all
from core.impact_settings import impact_settings
from core.schemas import CandidateAssessment, ChangeSeeds, ImpactAssessment
from tests.sandbox.fake_jira import FakeRepoHost, jira_client_over
from tests.sandbox.seed import build_repo, repo_files, seed_jira


def _settings(**over):
    s = impact_settings({})
    s.update(over)
    return s


@pytest.fixture
def world(tmp_path, monkeypatch):
    fake = seed_jira()
    fake.add("Story", "Wrong-password error now explains how to reset the password", key="SBX-5",
             labels=["impact-check"], components=["Login"],
             description="When the password is wrong, the error message also links to reset.")
    jira = jira_client_over(fake, monkeypatch)
    root = build_repo(tmp_path / "repo")
    import config.paths as paths
    monkeypatch.setattr(paths, "FEATURES_DIR", root / "features")
    monkeypatch.setattr(paths, "PROJECT_ROOT", root)
    a0._GRAPHS.clear()
    return fake, jira, root, build_impact_graph(root)


def _only_in(graph, key, other):
    """An element the scenario of `key` uses and the scenario of `other` does not."""
    diff = graph.scenario_for_key(key).elements - graph.scenario_for_key(other).elements
    return sorted(diff)[0]


class FakeModel:
    """Answers ChangeSeeds and ImpactAssessment from the prompt it is given."""

    def __init__(self, element_keys, must=(), no_evidence=(), invent=(), review=()):
        self.element_keys, self.must, self.no_evidence = list(element_keys), set(must), set(no_evidence)
        self.review = set(review)
        self.invent = list(invent)
        self.calls = []

    def invoke_structured(self, system_prompt, user_prompt, output_schema):
        self.calls.append(output_schema.__name__)
        if output_schema is ChangeSeeds:
            return ChangeSeeds(change_type="changed_behaviour", behaviours=["error text changes"],
                               element_keys=self.element_keys + self.invent, components=[])
        items = []
        for cid, title in re.findall(r"^## (C\d+) - (.+?) \(", user_prompt, re.M):
            paths = re.findall(r"^(P\d+): ", user_prompt.split(f"## {cid} - ", 1)[1].split("## C")[0], re.M)
            tier = ("must-update" if title in self.must
                    else "review" if title in self.review else "unaffected")
            refs = [] if title in self.no_evidence else (paths[:1] or ["Given I am on the signup and login page"])
            items.append(CandidateAssessment(candidate_id=cid, tier=tier, reason="r", evidence_refs=refs))
        return ImpactAssessment(assessments=items)


TITLE_12 = "Login fails with an incorrect password"


def _revise_on_branch(host, root, tmp_path, key):
    """Agent 2's pull request, reduced to what stage 10 reads: the marker of
    `key` gets a new hash on a branch. Returns the branch name and a local
    checkout of its features/ (what Agent 5 runs on)."""
    from agents.agent2_coder import build_marker_index
    entry = build_marker_index(root / "features").by_key[key]
    path = f"features/{entry.file}"
    name = f"auto/SBX-5-revise-{key.lower()}"
    host.create_branch(name)
    host.branches[name][path] = host.branches[name][path].replace(
        f"# JIRA: {key} (hash: {entry.hash})", f"# JIRA: {key} (hash: 0000ffff)")
    checkout = tmp_path / "checkout" / "features"
    shutil.copytree(root / "features", checkout)
    (checkout / entry.file).write_text(host.branches[name][path])
    return {"name": name, "features": checkout}


def _junit(root, key, status):
    """A junit result for the scenario of `key`, named as pytest-bdd names it."""
    from types import SimpleNamespace

    from agents.agent2_coder import build_marker_index
    from core.impact_results import _test_name
    entry = build_marker_index(root / "features").by_key[key]
    module = "test_" + entry.file.rsplit(".", 1)[0]
    return SimpleNamespace(classname=f"tests.step_defs.{module}", name=_test_name(entry.title),
                           status=status)


# ─────────────────────────────────────────────────────────────────
# D1 - code change and drift: structural only, no model
# ─────────────────────────────────────────────────────────────────
class TestD1:
    def test_a_changed_selector_finds_exactly_its_scenarios(self, world, tmp_path):
        _f, jira, root, g = world
        page, key = _only_in(g, "SBX-12", "SBX-11")
        head = tmp_path / "head"
        shutil.copytree(root, head)
        inv_path = next((head / "app_inventory").glob("*.json"))
        inv = json.loads(inv_path.read_text())
        inv["pages"][page]["elements"][key] = "[data-qa='renamed']"
        inv_path.write_text(json.dumps(inv))
        report = a0.analyse_code_change(root, head, "PR #9", _settings(), jira, None)
        tiers = {r["ref"]: r["tier"] for r in report["ranked"]}
        assert tiers["SBX-12"] == "must-update" and "SBX-11" not in tiers
        assert report["seeds"]["elements"] == [f"{page}:{key}"]
        assert next(r for r in report["ranked"] if r["ref"] == "SBX-12")["owner"] == "SBX-1"

    def test_a_changed_page_method_body_is_a_seed(self, world, tmp_path):
        _f, _jira, root, g = world
        head = tmp_path / "head"
        shutil.copytree(root, head)
        cls, name = sorted(g.scenario_for_key("SBX-12").methods - g.scenario_for_key("SBX-11").methods)[0]
        path = next(p for p in (head / "pages").glob("*.py") if f"class {cls}(" in p.read_text())
        src = path.read_text()
        src = re.sub(rf"(    def {name}\(self[^\n]*\n(?:\s*\"\"\"[\s\S]*?\"\"\"\n)?)",
                     r"\1        _changed = True\n", src, count=1)
        path.write_text(src)
        seeds = ia.code_change_seeds(root, head)
        assert (cls, name) in seeds.methods and len(seeds.methods) == 1

    def test_a_signature_change_beyond_positional_names_is_a_seed(self, world, tmp_path):
        """A keyword-only parameter, a default or a decorator changes how
        callers bind; comparing positional argument names alone missed it."""
        _f, _jira, root, g = world
        head = tmp_path / "head"
        shutil.copytree(root, head)
        cls, name = min(g.scenario_for_key("SBX-12").methods)
        path = next(p for p in (head / "pages").glob("*.py") if f"class {cls}(" in p.read_text())
        src = path.read_text()
        new = re.sub(rf"(    def {name}\(self)", r"\1, *, strict=False", src, count=1)
        assert new != src
        path.write_text(new)
        assert ia.code_change_seeds(root, head).methods == {(cls, name)}

    def test_moving_a_method_is_not_a_change(self, world, tmp_path):
        _f, _jira, root, _g = world
        head = tmp_path / "head"
        shutil.copytree(root, head)
        for path in (head / "pages").glob("*.py"):
            path.write_text("\n\n\n" + path.read_text())           # every line number moves
        assert ia.code_change_seeds(root, head).methods == set()

    def test_an_element_read_by_a_then_step_scores_higher(self, world):
        """Design stage 3: direct links such as an element used in an
        assertion score higher."""
        _f, _jira, _root, g = world
        asserted, other = None, None
        for s in g.scenarios:
            for el in sorted(s.elements):
                if ia._asserted(g, s, el[1]):
                    asserted = asserted or (s, el)
                else:
                    other = other or (s, el)
        assert asserted and other, "the sandbox suite has both kinds of link"
        for (s, el), expected, marker in ((asserted, ia.ASSERTED_ELEMENT, True),
                                          (other, ia.DIRECT_ELEMENT, False)):
            cand = next(c for c in ia.structural_candidates(g, ia.Seeds(elements={el}))
                        if c.ref == s.ref)
            assert cand.structural == expected
            assert ("Then step (assertion)" in cand.paths[0]["text"]) is marker
        assert ia.ASSERTED_ELEMENT > ia.DIRECT_ELEMENT > ia.PAGE_METHOD

    def test_drift_report_seeds(self, world):
        _f, jira, root, g = world
        page, key = _only_in(g, "SBX-12", "SBX-11")
        drift = {"pages": {page: {"missing": [{"element": key, "selector": "x"}]}},
                 "unreachable_pages": []}
        report = a0.analyse_drift(drift, root, _settings(), jira)
        assert "SBX-12" in {r["ref"] for r in report["ranked"]}

    def test_no_change_no_candidates(self, world):
        _f, jira, root, _g = world
        report = a0.analyse_code_change(root, root, "PR #1", _settings(), jira)
        assert report["ranked"] == [] and report["seeds"]["methods"] == []


# ─────────────────────────────────────────────────────────────────
# D3 - requirement trigger, layers 1-3, short-list rule
# ─────────────────────────────────────────────────────────────────
class TestD3:
    def test_requirement_analysis_ranks_and_checks_evidence(self, world):
        _f, jira, root, g = world
        page, key = _only_in(g, "SBX-12", "SBX-11")
        model = FakeModel([f"{page}:{key}"], must={TITLE_12}, invent=["nowhere:invented_key"])
        report = a0.analyse_requirement(jira, "SBX-5", model, _settings(), root)
        top = report["ranked"][0]
        assert top["ref"] == "SBX-12" and top["tier"] == "must-update"
        # 0.45*1.0 + 0.15*1.0 (component) + 0.15*semantic + 0.25*1.0 (must-update)
        assert top["score"] >= 0.85
        assert report["seeds"]["dropped"] == ["nowhere:invented_key"]
        assert model.calls == ["ChangeSeeds", "ImpactAssessment"]

    def test_an_assessment_without_evidence_is_dropped(self, world):
        _f, jira, root, g = world
        page, key = _only_in(g, "SBX-12", "SBX-11")
        model = FakeModel([f"{page}:{key}"], must={TITLE_12}, no_evidence={TITLE_12})
        report = a0.analyse_requirement(jira, "SBX-5", model, _settings(), root)
        assert any("cites no checkable evidence" in d for d in report["dropped_assessments"])
        row = next(r for r in report["ranked"] + report["unaffected"] if r["ref"] == "SBX-12")
        assert row["score"] < 0.85            # no adjudicated signal

    def test_shortlist_rule_with_no_component_and_a_small_cap(self, world):
        fake, jira, root, g = world
        fake.issues["SBX-5"]["components"] = []
        page, key = _only_in(g, "SBX-12", "SBX-11")
        n1 = len(g.scenarios_using_element(page, key))           # layer 1 size
        cap = n1 + 1                                              # room for ONE layer-2 candidate
        report = a0.analyse_requirement(jira, "SBX-5", FakeModel([f"{page}:{key}"]),
                                        _settings(max_candidates=cap), root)
        judged = report["ranked"] + report["unaffected"]
        layer1 = [r for r in judged if r["layer"] == 1]
        layer2 = [r for r in judged if r["layer"] == 2]
        assert len(layer1) == n1 and len(layer2) == 1 and len(judged) == cap
        assert report["no_component"] is True                    # whole suite considered
        assert len(report["not_judged"]) == g.stats()["scenarios"] - cap
        assert "SBX-12" in {r["ref"] for r in layer1}            # layer 1 always judged


    def test_layer1_is_never_dropped_beyond_the_cap(self, world):
        _f, jira, root, g = world
        # an element every login scenario uses -> many layer 1 candidates
        common = sorted(set.intersection(*[set(s.elements) for s in g.scenarios
                                          if s.file.endswith("sandbox_login.feature")]))[0]
        model = FakeModel([f"{common[0]}:{common[1]}"])
        report = a0.analyse_requirement(jira, "SBX-5", model, _settings(max_candidates=2), root)
        judged = report["ranked"] + report["unaffected"]
        assert len([r for r in judged if r["layer"] == 1]) > 2
        assert model.calls.count("ImpactAssessment") >= 2         # several calls of <= 2

    def test_no_component_comment_is_posted_once(self, world):
        fake, jira, root, g = world
        fake.issues["SBX-5"]["components"] = []
        page, key = _only_in(g, "SBX-12", "SBX-11")
        s = _settings()
        for n in range(2):
            fake.issues["SBX-5"]["description"] = f"edit {n}"     # new content each time
            a0.publish(jira, "SBX-5", a0.analyse_requirement(jira, "SBX-5",
                                                             FakeModel([f"{page}:{key}"]), s, root), s)
        assert len([c for c in fake.comments["SBX-5"] if c.startswith(a0.NO_COMPONENT)]) == 1


# ─────────────────────────────────────────────────────────────────
# Publishing, stage 0 guard, shadow mode
# ─────────────────────────────────────────────────────────────────
class TestPublish:
    def _report(self, jira, root, g, **over):
        page, key = _only_in(g, "SBX-12", "SBX-11")
        return a0.analyse_requirement(jira, "SBX-5", FakeModel([f"{page}:{key}"], must={TITLE_12}),
                                      _settings(**over), root)

    def test_shadow_mode_posts_a_report_only(self, world):
        fake, jira, root, g = world
        s = _settings()                                   # shadow_mode True by default
        r = a0.publish(jira, "SBX-5", self._report(jira, root, g), s)
        assert r["action"] == "shadow-report"
        assert fake.issues["SBX-5"]["labels"] == []        # trigger consumed, nothing added
        assert jira.get_subtasks("SBX-5") == []
        body = next(c for c in fake.comments["SBX-5"] if c.startswith(a0.REPORT))
        assert ia.extract(body)["ranked"][0]["ref"] == "SBX-12"

    def test_same_content_is_not_analysed_twice(self, world):
        _f, jira, root, g = world
        s = _settings()
        report = self._report(jira, root, g)
        a0.publish(jira, "SBX-5", report, s)
        assert a0.publish(jira, "SBX-5", report, s)["action"] == "unchanged"

    def test_stage0_guard_runs_before_any_model_call(self, world):
        """Design stage 0: 're-running is therefore free'."""
        fake, jira, root, g = world
        s = _settings()
        page, key = _only_in(g, "SBX-12", "SBX-11")
        model = FakeModel([f"{page}:{key}"], must={TITLE_12})
        assert a0.analyse_and_publish(jira, "SBX-5", model, s, root)["action"] == "shadow-report"
        calls = len(model.calls)
        fake.issues["SBX-5"]["labels"].append("impact-check")      # someone asks again
        assert a0.analyse_and_publish(jira, "SBX-5", model, s, root)["action"] == "unchanged"
        assert len(model.calls) == calls                           # no model call at all
        assert "impact-check" not in fake.issues["SBX-5"]["labels"]
        fake.issues["SBX-5"]["description"] += " Edited."                # an edit is new content
        fake.issues["SBX-5"]["labels"].append("impact-check")
        assert a0.analyse_and_publish(jira, "SBX-5", model, s, root)["action"] == "shadow-report"
        assert len(model.calls) > calls

    def test_a_shadow_report_does_not_count_once_shadow_mode_is_off(self, world):
        fake, jira, root, g = world
        page, key = _only_in(g, "SBX-12", "SBX-11")
        model = FakeModel([f"{page}:{key}"], must={TITLE_12})
        a0.analyse_and_publish(jira, "SBX-5", model, _settings(), root)
        fake.issues["SBX-5"]["labels"].append("impact-check")
        r = a0.analyse_and_publish(jira, "SBX-5", model, _settings(shadow_mode=False), root)
        assert r["action"] == "review-created" and len(jira.get_subtasks("SBX-5")) == 1

    def test_a_shadow_report_releases_the_story_to_agent1(self, world):
        from agents.agent1_analyst import load_agent_config
        fake, jira, root, g = world
        fake.issues["SBX-5"]["labels"].append("ai-ready")
        selection = dict(load_agent_config()["selection"])
        selection.pop("sprint", None)
        assert "SBX-5" not in {x["key"] for x in jira.find_stories_to_process(selection)}
        a0.publish(jira, "SBX-5", self._report(jira, root, g), _settings())
        assert "SBX-5" in {x["key"] for x in jira.find_stories_to_process(selection)}

    def test_live_mode_creates_the_review_grouped_by_owner(self, world):
        fake, jira, root, g = world
        s = _settings(shadow_mode=False)
        r = a0.publish(jira, "SBX-5", self._report(jira, root, g), s)
        assert r["action"] == "review-created"
        review = jira.get_subtasks("SBX-5")[0]
        rows = __import__("core.impact_review", fromlist=["x"]).parse_rows(review["description"])
        assert rows["SBX-12"]["owner"] == "SBX-1" and rows["SBX-12"]["decision"] == "approve"
        assert sorted(l for l in fake.issues["SBX-5"]["labels"] if l.startswith("impact-")) == \
            ["impact-proposed"]
        # stage 7: the ranked report is also on the change story, grouped by owner
        body = next(c for c in fake.comments["SBX-5"] if c.startswith(a0.REPORT))
        assert f"review {review['key']}" in body.splitlines()[0]
        posted = ia.extract(body)
        assert "SBX-12" in posted["by_owner"]["SBX-1"]
        assert posted["by_owner"] == ia.by_owner(posted["ranked"])
        assert "By owning story: " in body

    def test_nothing_to_review_makes_the_story_ready(self, world):
        fake, jira, root, _g = world
        empty = a0.analyse_requirement(jira, "SBX-5", FakeModel([]), _settings(), root)
        empty["ranked"] = []
        a0.publish(jira, "SBX-5", empty, _settings(shadow_mode=False))
        assert "ai-ready" in fake.issues["SBX-5"]["labels"]
        assert not [l for l in fake.issues["SBX-5"]["labels"] if l.startswith("impact-")]


# ─────────────────────────────────────────────────────────────────
# D4 - in-flight guard and delta re-analysis
# ─────────────────────────────────────────────────────────────────
class TestD4:
    def test_a_test_with_another_open_change_is_blocked(self, world):
        fake, jira, root, g = world
        host = FakeRepoHost({})
        host.open_pull_request("t", "b", "auto/SBX-3-clearer-error")   # SBX-3 impacts SBX-12
        page, key = _only_in(g, "SBX-12", "SBX-11")
        report = a0.analyse_requirement(jira, "SBX-5", FakeModel([f"{page}:{key}"], must={TITLE_12}),
                                        _settings(), root, host)
        row = next(r for r in report["ranked"] if r["ref"] == "SBX-12")
        assert row["blocked_by"] == ["SBX-3"]
        s = _settings(shadow_mode=False)
        a0.publish(jira, "SBX-5", report, s)
        review = jira.get_subtasks("SBX-5")[0]
        assert "blocked by SBX-3" in review["description"]
        fake.issues[review["key"]]["status"] = "Done"
        from core.impact_handover import HandoverRefused, decisions_from_review, handover
        key_, decisions = decisions_from_review(jira, "SBX-5")
        with pytest.raises(HandoverRefused, match="SBX-12"):
            handover(jira, "SBX-5", decisions, review_key=key_)

    def test_open_review_is_updated_keeping_decisions(self, world):
        fake, jira, root, g = world
        s = _settings(shadow_mode=False)
        page, key = _only_in(g, "SBX-12", "SBX-11")
        model = FakeModel([f"{page}:{key}"], must={TITLE_12})
        a0.publish(jira, "SBX-5", a0.analyse_requirement(jira, "SBX-5", model, s, root), s)
        review = jira.get_subtasks("SBX-5")[0]
        fake.issues[review["key"]]["description"] = review["description"].replace("|approve|", "|reject|")
        fake.issues["SBX-5"]["description"] += " Also on mobile."
        fake.issues["SBX-5"]["labels"].append("impact-check")
        r = a0.publish(jira, "SBX-5", a0.analyse_requirement(jira, "SBX-5", model, s, root), s)
        assert r["action"] == "review-updated" and len(jira.get_subtasks("SBX-5")) == 1
        assert __import__("core.impact_review", fromlist=["x"]).parse(
            jira.get_subtasks("SBX-5")[0]["description"])["SBX-12"] == "reject"

    def test_after_approval_a_new_review_lists_only_the_difference(self, world):
        fake, jira, root, g = world
        s = _settings(shadow_mode=False)
        page, key = _only_in(g, "SBX-12", "SBX-11")
        a0.publish(jira, "SBX-5", a0.analyse_requirement(
            jira, "SBX-5", FakeModel([f"{page}:{key}"], must={TITLE_12}), s, root), s)
        fake.issues[jira.get_subtasks("SBX-5")[0]["key"]]["status"] = "Done"
        p11, k11 = _only_in(g, "SBX-11", "SBX-12")
        fake.issues["SBX-5"]["description"] += " And the success banner changes."
        model = FakeModel([f"{page}:{key}", f"{p11}:{k11}"],
                          must={TITLE_12, "Successful login with valid credentials"})
        r = a0.publish(jira, "SBX-5", a0.analyse_requirement(jira, "SBX-5", model, s, root), s)
        assert r["action"] == "review-created"
        second = jira.get_subtasks("SBX-5")[-1]
        rows = __import__("core.impact_review", fromlist=["x"]).parse(second["description"])
        assert "SBX-11" in rows and "SBX-12" not in rows
        assert any(c.startswith(a0.DELTA) for c in fake.comments["SBX-5"])

    def test_after_approval_a_removal_alone_is_reported_and_the_story_released(self, world):
        """Agent 3 review of #131: with only removals there are no new rows.
        The DELTA comment must still say so, and impact-check must come off,
        or the next scan analyses the story again every day."""
        fake, jira, root, g = world
        s = _settings(shadow_mode=False)
        page, key = _only_in(g, "SBX-12", "SBX-11")
        p11, k11 = _only_in(g, "SBX-11", "SBX-12")
        both = {TITLE_12, "Successful login with valid credentials"}
        a0.publish(jira, "SBX-5", a0.analyse_requirement(
            jira, "SBX-5", FakeModel([f"{page}:{key}", f"{p11}:{k11}"], must=both), s, root), s)
        first = jira.get_subtasks("SBX-5")[0]
        assert set(__import__("core.impact_review", fromlist=["x"]).parse(first["description"])) \
            == {"SBX-11", "SBX-12"}
        fake.issues[first["key"]]["status"] = "Done"
        fake.issues["SBX-5"]["labels"] = ["ai-ready", "impact-check"]     # re-analysis asked for
        fake.issues["SBX-5"]["description"] += " The success banner is not touched after all."
        r = a0.publish(jira, "SBX-5", a0.analyse_requirement(
            jira, "SBX-5", FakeModel([f"{page}:{key}"], must={TITLE_12}), s, root), s)
        assert r == {"story": "SBX-5", "action": "no-new-impact", "review": first["key"]}
        assert len(jira.get_subtasks("SBX-5")) == 1
        delta = [c for c in fake.comments["SBX-5"] if c.startswith(a0.DELTA)]
        assert len(delta) == 1 and "removed [" in delta[0] and "added []" in delta[0]
        assert f"approved review {first['key']} stands" in delta[0]
        assert fake.issues["SBX-5"]["labels"] == ["ai-ready"]             # released, unchanged
        assert "SBX-5" not in {x["key"] for x in jira.find_stories_to_process(s["selection"])}

    def test_after_approval_nothing_ranked_still_reports_the_removal(self, world):
        fake, jira, root, g = world
        s = _settings(shadow_mode=False)
        page, key = _only_in(g, "SBX-12", "SBX-11")
        a0.publish(jira, "SBX-5", a0.analyse_requirement(
            jira, "SBX-5", FakeModel([f"{page}:{key}"], must={TITLE_12}), s, root), s)
        fake.issues[jira.get_subtasks("SBX-5")[0]["key"]]["status"] = "Done"
        fake.issues["SBX-5"]["description"] += " Withdrawn: the error text stays."
        r = a0.publish(jira, "SBX-5", a0.analyse_requirement(
            jira, "SBX-5", FakeModel([]), s, root), s)
        assert r["action"] == "nothing-to-review"
        assert any(c.startswith(a0.DELTA) and "removed [" in c and "removed []" not in c
                   for c in fake.comments["SBX-5"])


def test_cli_code_change_posts_once_per_distinct_change(world, monkeypatch, tmp_path):
    """Stage 0 for code changes: each push re-runs the workflow; the same
    seeds are not reported on the pull request twice."""
    _fake, jira, root, g = world
    s = _settings(enabled=True)
    host = FakeRepoHost(repo_files(root))
    host.open_pull_request("t", "b", "feature/x")
    import dotenv

    import integrations.repo_host as rh
    monkeypatch.setattr(a0, "impact_settings", lambda *a, **k: s)
    monkeypatch.setattr(a0, "get_tracker", lambda *a, **k: jira)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(rh, "get_repo_host", lambda *a, **k: host)
    head = tmp_path / "head"
    shutil.copytree(root, head)
    page, key = _only_in(g, "SBX-12", "SBX-11")
    inv_path = next((head / "app_inventory").glob("*.json"))
    inv = json.loads(inv_path.read_text())
    inv["pages"][page]["elements"][key] = "#changed"
    inv_path.write_text(json.dumps(inv))
    argv = ["--code-change", "--base", str(root), "--head", str(head), "--pr", "1"]
    assert a0.main(argv) == 0 and a0.main(argv) == 0
    assert len(host.get_pr_comments(1)) == 1                       # the push changed nothing
    inv["pages"][page]["elements"][key] = "#changed-again"         # same seeds: same element
    inv_path.write_text(json.dumps(inv))
    assert a0.main(argv) == 0 and len(host.get_pr_comments(1)) == 1
    other_page, other_key = _only_in(g, "SBX-11", "SBX-12")        # a new seed
    inv["pages"][other_page]["elements"][other_key] = "#also"
    inv_path.write_text(json.dumps(inv))
    assert a0.main(argv) == 0 and len(host.get_pr_comments(1)) == 2


class TestDriftCli:
    """The nightly drift job, live: one maintenance story carries the drift
    for as long as it lasts (Agent 3 review of #131)."""

    @pytest.fixture
    def cli(self, world, monkeypatch, tmp_path):
        fake, jira, root, g = world
        s = _settings(enabled=True, shadow_mode=False)
        monkeypatch.setattr(a0, "impact_settings", lambda *a, **k: s)
        monkeypatch.setattr(a0, "get_tracker", lambda *a, **k: jira)
        import dotenv

        import integrations.repo_host as rh
        monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
        monkeypatch.setattr(rh, "get_repo_host", lambda *a, **k: FakeRepoHost(repo_files(root)))

        def run(*elements):
            path = tmp_path / "drift.json"
            pages: dict = {}
            for page, key in elements:
                pages.setdefault(page, {"missing": []})["missing"].append({"element": key})
            path.write_text(json.dumps({"pages": pages, "unreachable_pages": []}))
            assert a0.main(["--drift-report", str(path)]) == 0

        return fake, jira, g, run

    @staticmethod
    def _drift_stories(fake):
        return [i for i in fake.issues.values() if i["summary"] == "Maintenance: inventory drift"]

    def test_first_drift_creates_a_labelled_story_with_a_review(self, cli, capsys):
        fake, jira, g, run = cli
        page, key = _only_in(g, "SBX-12", "SBX-11")
        run((page, key))
        (story,) = self._drift_stories(fake)
        assert story["components"] == sorted(g.page_components[page])     # A1 template
        assert story["components"] and f"{page}:{key}" in story["description"]
        assert "inventory-drift" in story["labels"] and "impact-proposed" in story["labels"]
        assert "impact-check" not in story["labels"]
        assert len(jira.get_subtasks(story["key"])) == 1
        assert "'action': 'review-created'" in capsys.readouterr().out

    def test_the_same_drift_next_night_reuses_the_story(self, cli, capsys):
        fake, jira, g, run = cli
        element = _only_in(g, "SBX-12", "SBX-11")
        run(element)
        run(element)
        (story,) = self._drift_stories(fake)
        assert len(jira.get_subtasks(story["key"])) == 1
        assert "'action': 'unchanged'" in capsys.readouterr().out.splitlines()[-1]

    def test_new_drift_updates_the_open_review_on_the_same_story(self, cli, capsys):
        fake, jira, g, run = cli
        run(_only_in(g, "SBX-12", "SBX-11"))
        run(_only_in(g, "SBX-12", "SBX-11"), _only_in(g, "SBX-11", "SBX-12"))
        (story,) = self._drift_stories(fake)
        assert len(jira.get_subtasks(story["key"])) == 1
        assert "'action': 'review-updated'" in capsys.readouterr().out.splitlines()[-1]

    def test_a_closed_drift_story_is_not_reused(self, cli):
        fake, _jira, g, run = cli
        run(_only_in(g, "SBX-12", "SBX-11"))
        self._drift_stories(fake)[0]["status"] = "Done"
        run(_only_in(g, "SBX-11", "SBX-12"))
        assert len(self._drift_stories(fake)) == 2


# ─────────────────────────────────────────────────────────────────
# D5 - the live loop, and the switches
# ─────────────────────────────────────────────────────────────────
class TestD5:
    def test_disabled_scan_does_nothing(self, world):
        fake, jira, root, _g = world
        before = (dict(fake.comments), list(fake.issues["SBX-5"]["labels"]))
        assert a0.scan(jira, FakeRepoHost({}), MagicMock(), _settings(), root) == []
        assert (dict(fake.comments), list(fake.issues["SBX-5"]["labels"])) == before

    def test_shadow_scan_reports_and_stops(self, world):
        fake, jira, root, g = world
        page, key = _only_in(g, "SBX-12", "SBX-11")
        out = a0.scan(jira, FakeRepoHost({}), FakeModel([f"{page}:{key}"], must={TITLE_12}),
                      _settings(enabled=True), root)
        assert [r["action"] for r in out] == ["shadow-report"]
        assert jira.get_subtasks("SBX-5") == [] and "impact-check" not in fake.issues["SBX-5"]["labels"]
        assert a0.scan(jira, FakeRepoHost({}), MagicMock(), _settings(enabled=True), root) == []

    def test_live_loop_review_handover_reconcile_outcome(self, world, tmp_path):
        fake, jira, root, g = world
        s = _settings(enabled=True, shadow_mode=False)
        host = FakeRepoHost(repo_files(root))
        page, key = _only_in(g, "SBX-12", "SBX-11")
        model = FakeModel([f"{page}:{key}"], must={TITLE_12})

        out = a0.scan(jira, host, model, s, root)                       # analyse + publish
        assert out[0]["action"] == "review-created"
        review = jira.get_subtasks("SBX-5")[0]
        out = a0.scan(jira, host, model, s, root)                       # review still open
        assert any(r.get("action") == "waiting" for r in out)

        fake.issues[review["key"]]["status"] = "Done"                   # the person decides
        out = a0.scan(jira, host, model, s, root)
        assert {"story": "SBX-5", "action": "handed-over", "review": review["key"]} in out
        assert "ai-ready" in fake.issues["SBX-5"]["labels"]
        assert [c["key"] for c in jira.get_impacted_test_cases("SBX-5")] == ["SBX-12"]

        # (Agents 1 and 2 run here - tested in test_agent1_impact / test_agent2_impact)
        jira.remove_label("SBX-5", "ai-ready")
        jira.add_label("SBX-5", "impact-applied")
        branch = _revise_on_branch(host, root, tmp_path, "SBX-12")    # Agent 2's PR
        url = host.open_pull_request("t", "b", branch["name"])

        # Agent 4 runs the branch; Agent 5 records the outcome (stage 10)
        from core.impact_results import record_prediction_outcome
        failed_11 = _junit(root, "SBX-11", "failed")                  # broke, not predicted
        out = record_prediction_outcome(jira, host, "SBX-5", 1, url, [failed_11],
                                        branch["features"], s)
        assert out["actual_changed"] == ["SBX-12"] and out["actual_failed"] == ["SBX-11"]
        assert (out["recall"], out["precision"]) == (0.5, 1.0)
        assert record_prediction_outcome(jira, host, "SBX-5", 1, url, [failed_11],
                                         branch["features"], s) is None    # once per PR
        assert len([c for c in fake.comments["SBX-5"] if c.startswith(a0.OUTCOME)]) == 1

        host.merge(1)
        assert not [r for r in a0.scan(jira, host, model, s, root)      # reconcile is not
                    if r.get("action") == "merged"]                      # the scan's job
        # reconcile has its own job (C7)
        assert {"story": "SBX-5", "action": "merged", "pr": 1} in reconcile_all(jira, host, s)
        assert not [l for l in fake.issues["SBX-5"]["labels"] if l.startswith("impact-")]

    def test_shadow_mode_measures_too(self, world, tmp_path):
        """Design section 10: the targets must also hold over two sprints of
        shadow mode, so shadow predictions are measured when the PR runs."""
        _fake, jira, root, g = world
        s = _settings(enabled=True)                                    # shadow
        host = FakeRepoHost(repo_files(root))
        page, key = _only_in(g, "SBX-12", "SBX-11")
        a0.scan(jira, host, FakeModel([f"{page}:{key}"], must={TITLE_12}), s, root)
        branch = _revise_on_branch(host, root, tmp_path, "SBX-12")
        url = host.open_pull_request("t", "b", branch["name"])
        from core.impact_results import record_prediction_outcome
        out = record_prediction_outcome(jira, host, "SBX-5", 1, url, [], branch["features"], s)
        assert (out["recall"], out["precision"]) == (1.0, 1.0)

    def test_no_prediction_or_agent0_off_records_nothing(self, world, tmp_path):
        fake, jira, root, _g = world
        host = FakeRepoHost(repo_files(root))
        branch = _revise_on_branch(host, root, tmp_path, "SBX-12")
        host.open_pull_request("t", "b", branch["name"])
        from core.impact_results import record_prediction_outcome
        for s in (_settings(enabled=True), _settings()):               # no report; off
            assert record_prediction_outcome(jira, host, "SBX-5", 1, "u", [],
                                             branch["features"], s) is None
        assert not [c for c in fake.comments.get("SBX-5", []) if c.startswith(a0.OUTCOME)]

    def test_cli_is_a_no_op_while_disabled(self, capsys, monkeypatch):
        # Off explicitly: a project may ship Agent 0 on; the off path must hold.
        import core.impact_settings as settings_module
        real = settings_module.impact_settings
        monkeypatch.setattr(settings_module, "impact_settings",
                            lambda raw=None: real({**(raw or {}), "enabled": False}))
        if hasattr(a0, "impact_settings"):
            monkeypatch.setattr(a0, "impact_settings",
                                lambda raw=None: real({**(raw or {}), "enabled": False}))
        assert a0.main(["--scan"]) == 0
        assert "enabled is false" in capsys.readouterr().out


def test_layer2_fills_the_cap_most_relevant_first_and_reports_the_rest():
    def cand(ref, title, layer):
        return ia.Candidate(id="", ref=ref, test_case_key=ref, file="f", title=title,
                            steps=[], layer=layer)
    l1 = [cand("A", "anything at all", 1)]
    l2 = [cand("B", "cart totals update", 2), cand("C", "password reset link in error", 2),
          cand("D", "password error message shown", 2)]
    judged, rest = ia.shortlist(l1, l2, "wrong password error links to password reset", 3)
    assert [c.ref for c in judged] == ["A", "C", "D"]          # layer 1 first, then by overlap
    assert [c.ref for c in rest] == ["B"]                      # reported, not dropped
    assert [c.id for c in judged] == ["C1", "C2", "C3"]
    judged, rest = ia.shortlist(l1 * 1, l2, "x", 0)            # a zero cap still judges layer 1
    assert [c.ref for c in judged] == ["A"] and len(rest) == 3

def test_report_groups_by_owner_and_keeps_the_unowned():
    rows = [{"ref": "A-3", "owner": "A-1"}, {"ref": "f::t", "owner": None},
            {"ref": "A-4", "owner": "A-1"}, {"ref": "B-9", "owner": "B-2"}]
    assert ia.by_owner(rows) == {ia.UNOWNED: ["f::t"], "A-1": ["A-3", "A-4"], "B-2": ["B-9"]}


def test_outcome_and_delta_math():
    assert ia.outcome(["A", "B"], ["B"], ["C"]) == {
        "predicted": ["A", "B"], "actual_changed": ["B"], "actual_failed": ["C"],
        "recall": 0.5, "precision": 0.5}
    assert ia.outcome(["B"], ["B"], ["B"])["recall"] == 1.0          # changed and failed: once
    assert ia.outcome([], []) == {"predicted": [], "actual_changed": [], "actual_failed": [],
                                  "recall": None, "precision": None}
    d = ia.delta({"ranked": [{"ref": "a", "tier": "review"}, {"ref": "b", "tier": "review"}]},
                 {"ranked": [{"ref": "a", "tier": "must-update"}, {"ref": "c", "tier": "review"}]})
    assert [r["ref"] for r in d["added"]] == ["c"] and [r["ref"] for r in d["removed"]] == ["b"]
    assert d["tier_changed"] == [{"ref": "a", "from": "review", "to": "must-update"}]


def test_ranking_matches_the_design_example():
    """Design section 7: TEST-3 = 0.405 + 0.15 + 0.123 + 0.25 = 0.928."""
    c = ia.Candidate(id="C1", ref="T-3", test_case_key="T-3", file="f", title="t", steps=[],
                     layer=1, structural=0.9, component=1.0, semantic=0.82)
    rows = ia.rank([c], {"C1": ("must-update", "r", ["P1"])}, impact_settings({})["weights"],
                   impact_settings({})["thresholds"])
    assert rows[0]["score"] == 0.928 and rows[0]["tier"] == "must-update"


# ─────────────────────────────────────────────────────────────────
# E1 follow-up - uncovered-element hint (gated, review tier only)
# ─────────────────────────────────────────────────────────────────
class TestUncoveredHint:
    """The model stays in charge. The hint only adds a PAGE seed, which raises a
    candidate's structural signal; it never creates a verdict."""

    @staticmethod
    def _story_names_hint(fake):
        fake.issues["SBX-5"]["description"] = (
            "When the password is wrong, the error shows a reset hint for the user.")

    @staticmethod
    def _rows(report):
        return {r["ref"]: r for r in report["ranked"] + report["unaffected"]}

    def test_the_model_clearing_everything_still_clears_everything(self, world):
        """The hint cannot manufacture an affected test: if the model says
        unaffected, the tier stays unaffected however high the signal goes."""
        fake, jira, root, g = world
        page, _ = _only_in(g, "SBX-12", "SBX-11")
        self._story_names_hint(fake)
        on = a0.analyse_requirement(jira, "SBX-5", FakeModel([]), _settings(uncovered_hint=True),
                                    root, uncovered={page: {"reset_hint": "text=Reset"}})
        assert all(r["tier"] == "unaffected" for r in on["ranked"] + on["unaffected"])

    def test_the_hint_raises_the_signal_on_the_hinted_page_only(self, world):
        fake, jira, root, g = world
        page, _ = _only_in(g, "SBX-12", "SBX-11")
        self._story_names_hint(fake)
        off = self._rows(a0.analyse_requirement(jira, "SBX-5", FakeModel([]), _settings(), root))
        on = self._rows(a0.analyse_requirement(
            jira, "SBX-5", FakeModel([]), _settings(uncovered_hint=True), root,
            uncovered={page: {"reset_hint": "text=Reset"}}))
        assert on["SBX-12"]["score"] > off["SBX-12"]["score"]
        # SBX-11 also visits the hinted page, so it rises too: the page signal
        # reaches every scenario that visits the page, by design.
        assert on["SBX-11"]["score"] >= off["SBX-11"]["score"]

    def test_the_hint_never_produces_a_must_update_by_itself(self, world):
        fake, jira, root, g = world
        page, _ = _only_in(g, "SBX-12", "SBX-11")
        self._story_names_hint(fake)
        model = FakeModel([], review={TITLE_12})          # model: review, not must-update
        on = a0.analyse_requirement(jira, "SBX-5", model, _settings(uncovered_hint=True),
                                    root, uncovered={page: {"reset_hint": "text=Reset"}})
        assert all(r["tier"] != "must-update" for r in on["ranked"] + on["unaffected"])
        assert self._rows(on)["SBX-12"]["tier"] == "review"

    def test_a_name_the_story_does_not_say_changes_nothing(self, world):
        _fake, jira, root, g = world
        page, _ = _only_in(g, "SBX-12", "SBX-11")
        off = self._rows(a0.analyse_requirement(jira, "SBX-5", FakeModel([]), _settings(), root))
        on = self._rows(a0.analyse_requirement(
            jira, "SBX-5", FakeModel([]), _settings(uncovered_hint=True), root,
            uncovered={page: {"invoice_total": "text=Total"}}))
        assert {k: v["score"] for k, v in off.items()} == {k: v["score"] for k, v in on.items()}

    def test_the_flag_is_off_in_the_shipped_config(self):
        import yaml

        from config.paths import CONFIG_YAML
        cfg = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8"))

        def find(node):
            if isinstance(node, dict):
                if "uncovered_hint" in node:
                    return node["uncovered_hint"]
                return next((v for v in (find(x) for x in node.values()) if v is not None), None)
            return None
        assert find(cfg) is False
