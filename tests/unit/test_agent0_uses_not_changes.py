"""Agent 0: a story that USES existing behaviour does not change it.

A journey story (sign in, search, add, remove, sign out) combines behaviours
that already exist. Every existing test of those behaviours still passes once
it ships, so nothing is impacted. A validation run listed every element the
journey uses as a change seed, and ten existing test cases reached the review
table on overlap alone ("covers behaviours in scope").

The rule, enforced at both model steps and in code:
  seeds        a story the model classifies new_behaviour seeds nothing
  adjudication with no changed behaviour, a candidate is unaffected unless a
               step contradicts the story; review / must-update name the
               difference

No application name is written here: elements are taken from the graph.
"""
import re

import agents.agent0_impact as a0
from core import impact_analysis as ia
from core.schemas import CandidateAssessment, ChangeSeeds, ImpactAssessment
from config.paths import PROMPTS_DIR
from tests.unit.test_agent0 import TITLE_12, _only_in, _settings, world  # noqa: F401


class JourneyModel:
    """Seeds as the validation run produced them: elements the story uses,
    plus behaviours - under the given change_type. Adjudication answers from
    `tiers` (title -> tier), unaffected otherwise, and keeps every prompt."""

    def __init__(self, change_type, element_keys, tiers=None):
        self.change_type, self.element_keys = change_type, list(element_keys)
        self.tiers = dict(tiers or {})
        self.prompts = []

    def invoke_structured(self, system_prompt, user_prompt, output_schema):
        self.prompts.append((output_schema.__name__, user_prompt))
        if output_schema is ChangeSeeds:
            return ChangeSeeds(change_type=self.change_type,
                               behaviours=["user signs in", "user adds a product"],
                               element_keys=self.element_keys, components=[])
        items = []
        for cid, title in re.findall(r"^## (C\d+) - (.+?) \(", user_prompt, re.M):
            body = user_prompt.split(f"## {cid} - ", 1)[1].split("## C")[0]
            refs = re.findall(r"^(P\d+): ", body, re.M)[:1] or \
                [re.search(r"^  (.+)$", body, re.M).group(1)]
            items.append(CandidateAssessment(candidate_id=cid,
                                             tier=self.tiers.get(title, "unaffected"),
                                             reason="r", evidence_refs=refs))
        return ImpactAssessment(assessments=items)

    def adjudication_prompts(self):
        return [p for n, p in self.prompts if n == "ImpactAssessment"]


def _seed(g):
    page, key = _only_in(g, "SBX-12", "SBX-11")
    return f"{page}:{key}"


class TestNewBehaviourSeedsNothing:
    def test_a_new_behaviour_story_has_no_element_seed_and_no_changed_behaviour(self, world):
        _f, jira, root, g = world
        model = JourneyModel("new_behaviour", [_seed(g)])
        report = a0.analyse_requirement(jira, "SBX-5", model, _settings(), root)
        assert report["seeds"]["elements"] == []
        assert not [r for r in report["ranked"] + report["unaffected"] if r["layer"] == 1]
        for prompt in model.adjudication_prompts():
            assert "Behaviours it changes:\n(none)" in prompt

    def test_the_same_seeds_as_a_changed_behaviour_still_find_the_test(self, world):
        """The guard is the classification, not the seeds: a real change
        keeps its structural candidates and reaches must-update."""
        _f, jira, root, g = world
        model = JourneyModel("changed_behaviour", [_seed(g)], tiers={TITLE_12: "must-update"})
        report = a0.analyse_requirement(jira, "SBX-5", model, _settings(), root)
        assert report["seeds"]["elements"] == [_seed(g)]
        top = report["ranked"][0]
        assert top["ref"] == "SBX-12" and top["tier"] == "must-update"
        assert "user signs in" in model.adjudication_prompts()[0]

    def test_mixed_and_removed_keep_their_seeds(self):
        class G:
            inventory_elements = {("p", "k")}
        for kind in ("mixed", "removed_behaviour", "changed_behaviour"):
            seeds = ia.validate_requirement_seeds(
                ChangeSeeds(change_type=kind, behaviours=["b"], element_keys=["p:k"]), G(), [])
            assert seeds.elements == {("p", "k")} and seeds.behaviours == ["b"]

    def test_a_journey_story_judged_unaffected_is_released_with_no_review(self, world):
        fake, jira, root, g = world
        model = JourneyModel("new_behaviour", [_seed(g)])
        report = a0.analyse_requirement(jira, "SBX-5", model, _settings(), root)
        result = a0.publish(jira, "SBX-5", report, _settings(shadow_mode=False))
        assert result["action"] == "nothing-to-review"
        assert "ai-ready" in fake.issues["SBX-5"]["labels"]
        assert not [s for s in fake.issues.values()
                    if s.get("summary", "").startswith("Impact Review")]


class TestPromptsSayUsesIsNotChanges:
    def test_the_seeds_prompt_separates_using_from_changing(self):
        text = (PROMPTS_DIR / "agent0_seeds.md").read_text(encoding="utf-8")
        assert "Using a behaviour is not changing it" in text
        assert "would an existing test of that behaviour still pass, unchanged" in text
        assert "`change_type` is `new_behaviour` and `element_keys` and `behaviours` are empty" in text

    def test_the_adjudication_prompt_rejects_overlap_and_needs_a_named_difference(self):
        text = (PROMPTS_DIR / "agent0_adjudicate.md").read_text(encoding="utf-8")
        assert "# Overlap is not impact" in text
        assert "`reason` must name what the scenario does or checks that the change makes different" in text
        assert 'When the behaviours it changes are "(none)"' in text
        # the "(none)" the rule refers to is what the code substitutes
        src = (PROMPTS_DIR.parent / "agents" / "agent0_impact.py").read_text(encoding="utf-8")
        assert 'or "(none)")' in src

    def test_the_schema_defines_new_behaviour_as_nothing_existing_changing(self):
        desc = ChangeSeeds.model_fields["change_type"].description
        assert "nothing that exists today works differently" in desc
        assert "new journey through existing behaviour" in desc
