"""Every gate agrees with every other gate: each canonical answer passes the
WHOLE Agent 2 gate, and every remedy a gate names passes it too.

WHY THIS EXISTS
    Validators were added one at a time, each tested on its own. Nothing
    checked them AGAINST EACH OTHER. In validation story A3 two of them told
    the model opposite things about one absence check - one demanded a
    presence wait, the other rejected it - so no rewrite could pass, the
    repair loop stalled, and Agent 2 failed. Every test of each rule was
    green.

    This file runs the REAL gate (`_validate_generated_files`, the function
    that failed in CI) on:
      1. the canonical shape of each common concern - a presence check, an
         absence check, a waiting reader - which must pass untouched;
      2. each known wrong shape, which must fail AND name a remedy; the
         remedy applied must then pass the whole gate.

    A new validator that rejects a canonical shape, or a remedy that another
    validator rejects, fails here - in CI, before any story run.

    Keys come from the configured inventory at run time; nothing here names
    an application.
"""
import re
from pathlib import Path

import pytest

import agents.agent2_coder as a2
from validators.method_resolution_validator import _load_configured_inventory

ROOT = Path(__file__).resolve().parents[2]


def _a_page_and_key():
    """An inventory page with one single-match, non-conditional element."""
    inv = _load_configured_inventory(ROOT) or {}
    for name, page in sorted((inv.get("pages") or {}).items()):
        if not isinstance(page, dict):
            continue
        multi = set(page.get("multi_match") or [])
        cond = set(page.get("conditional") or [])
        for key in (page.get("elements") or {}):
            if key not in multi and key not in cond and not key.startswith("_"):
                return name, key
    pytest.skip("no inventory page with a plain element")


PAGE_NAME, KEY = _a_page_and_key()
STEM = "gate_agreement"
CLASS = "GateAgreementPage"
FIXTURE = "gate_agreement_page"


def _batch(methods: str, step_body: str):
    page = (f"from pages.base_page import BasePage\n\n\n"
            f"class {CLASS}(BasePage):\n"
            f"    \"\"\"Synthetic page object for the gate-agreement contract.\"\"\"\n\n"
            f"    INVENTORY_PAGE = \"{PAGE_NAME}\"\n\n{methods}")
    feature = (f"Feature: Gate agreement\n\n"
               f"  Scenario: the element answers the question\n"
               f"    Then the element answers the question\n")
    steps = (f"from pytest_bdd import scenarios, then\n\n"
             f"from config.paths import feature_path\n\n"
             f"scenarios(str(feature_path(\"{STEM}\")))\n\n\n"
             f"@then(\"the element answers the question\")\n"
             f"def element_answers({FIXTURE}) -> None:\n"
             f"    {step_body}\n")
    return [a2.GeneratedFile(file_path=f"pages/{STEM}_page.py", content=page,
                             is_new_file=True, purpose="contract"),
            a2.GeneratedFile(file_path=f"features/{STEM}.feature", content=feature,
                             is_new_file=True, purpose="contract"),
            a2.GeneratedFile(file_path=f"tests/step_defs/test_{STEM}.py", content=steps,
                             is_new_file=True, purpose="contract")]


def _gate(files):
    """Every error the production gate would raise on, as one list."""
    try:
        a2._validate_generated_files(files, "CONTRACT-1")
        return []
    except ValueError as e:
        return [str(e)]


def _method(name, body):
    return (f"    def {name}(self) -> bool:\n"
            f"        \"\"\"Answer one question about the element.\"\"\"\n"
            f"        return {body}\n")


SEL = f'self.sel("{KEY}")'

CANONICAL = {
    "presence check": (_method("is_element_shown", f"self.is_showing({SEL})"),
                       f"assert {FIXTURE}.is_element_shown(), \"Expected the element\""),
    "absence check": (_method("is_element_absent", f"self.is_gone({SEL})"),
                      f"assert {FIXTURE}.is_element_absent(), \"Expected no element\""),
}


@pytest.fixture(autouse=True)
def _features_dir(tmp_path, monkeypatch):
    """The step file binds its feature by path; point that at a scratch dir."""
    import config.paths as paths
    (tmp_path / f"{STEM}.feature").write_text("Feature: x\n", encoding="utf-8")
    monkeypatch.setattr(paths, "FEATURES_DIR", tmp_path, raising=False)


@pytest.mark.parametrize("concern", sorted(CANONICAL))
def test_the_canonical_answer_passes_the_whole_gate(concern):
    methods, step = CANONICAL[concern]
    assert _gate(_batch(methods, step)) == [], (
        f"the whole Agent 2 gate rejects the canonical {concern}: a model "
        f"writing the shape the prompt teaches would fail. Some validator "
        f"disagrees with the others - fix the validator, not this test.")


# (label, wrong methods, wrong step, the call the error must name, fixed methods, fixed step)
REMEDIES = [
    ("absence by negated glance",
     _method("is_element_absent", f"not self.is_visible({SEL})"),
     f"assert {FIXTURE}.is_element_absent()",
     "is_gone", *CANONICAL["absence check"]),
    ("presence by glance",
     _method("is_element_shown", f"self.is_visible({SEL})"),
     f"assert {FIXTURE}.is_element_shown()",
     "is_showing", *CANONICAL["presence check"]),
    ("absence through a presence wait",
     _method("is_element_shown", f"self.is_showing({SEL})"),
     f"assert not {FIXTURE}.is_element_shown()",
     "is_gone", *CANONICAL["absence check"]),
]


@pytest.mark.parametrize("label,wrong_m,wrong_s,named,fix_m,fix_s", REMEDIES,
                         ids=[r[0] for r in REMEDIES])
def test_every_named_remedy_passes_the_whole_gate(label, wrong_m, wrong_s, named, fix_m, fix_s,
                                                  caplog):
    caplog.set_level("ERROR")
    errors = _gate(_batch(wrong_m, wrong_s))
    assert errors, f"the gate let the wrong shape through: {label}"
    said = caplog.text + " ".join(errors)
    assert re.search(rf"\b{named}\(", said), (
        f"the gate rejected {label!r} but did not name {named}() as the fix")
    assert _gate(_batch(fix_m, fix_s)) == [], (
        f"the remedy the gate names for {label!r} is itself rejected by the "
        f"gate - the model would loop between two rules (validation story A3)")
