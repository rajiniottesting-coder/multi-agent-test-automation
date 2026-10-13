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
      1. the canonical shape of each common concern the generation prompt
         teaches - presence, absence, a waiting reader, readiness, a row
         listed or gone, an exact count, "are there any" - which must pass
         untouched;
      2. each known wrong shape, which must fail AND name its remedy; the
         remedy applied must then pass the whole gate.

    A new validator that rejects a canonical shape, or a remedy another
    validator rejects, fails here - in CI, before any story run.

    WHEN YOU ADD A VALIDATOR OR CHANGE A REMEDY: add its canonical shape to
    CANONICAL and its wrong-to-right pair to REMEDIES.

    Page and keys come from the configured inventory at run time; nothing
    here names an application.
"""
import re
from pathlib import Path

import pytest

import agents.agent2_coder as a2
from validators.method_resolution_validator import _load_configured_inventory

ROOT = Path(__file__).resolve().parents[2]


def _inventory_choice():
    """A page with an unconditional multi-match family and a plain (single,
    unconditional) element - every concern below needs one or the other."""
    inv = _load_configured_inventory(ROOT) or {}
    for name, page in sorted((inv.get("pages") or {}).items()):
        if not isinstance(page, dict):
            continue
        cond = set(page.get("conditional") or [])
        # An UNCONDITIONAL family: the predicate rule rightly lets a glance
        # through for a family the inventory declares may legitimately be
        # absent, so a conditional one would hide the rule being checked.
        multi = [k for k in (page.get("multi_match") or [])
                 if not k.startswith("_") and k not in cond]
        plain = [k for k in (page.get("elements") or {})
                 if k not in multi and k not in cond and not k.startswith("_")]
        if len(multi) >= 2 and plain:
            # the second family serves as the control inside an entry
            return name, plain[0], multi[0], page.get("readiness") or plain[0], multi[-1]
    pytest.skip("no inventory page with both a family and a plain element")


PAGE_NAME, KEY, FAMILY, READY, CONTROL = _inventory_choice()
STEM = "gate_agreement"
CLASS = "GateAgreementPage"
FX = "gate_agreement_page"
SEL = f'self.sel("{KEY}")'
FAM = f'self.sel("{FAMILY}")'
CTRL = f'self.sel("{CONTROL}")'


def _batch(methods: str, step_line: str, phrase: str, decorator_arg: str, params: str = ""):
    page = (f"from pages.base_page import BasePage\n\n\n"
            f"class {CLASS}(BasePage):\n"
            f"    \"\"\"Synthetic page object for the gate-agreement contract.\"\"\"\n\n"
            f"    INVENTORY_PAGE = \"{PAGE_NAME}\"\n\n{methods}")
    feature = (f"Feature: Gate agreement\n\n"
               f"  Scenario: the page answers the question\n"
               f"    Then {phrase}\n")
    steps = (f"from pytest_bdd import parsers, scenarios, then\n\n"
             f"from config.paths import feature_path\n\n"
             f"scenarios(str(feature_path(\"{STEM}\")))\n\n\n"
             f"@then({decorator_arg})\n"
             f"def page_answers({FX}{params}) -> None:\n"
             f"    {step_line}\n")
    return [a2.GeneratedFile(file_path=f"pages/{STEM}_page.py", content=page,
                             is_new_file=True, purpose="contract"),
            a2.GeneratedFile(file_path=f"features/{STEM}.feature", content=feature,
                             is_new_file=True, purpose="contract"),
            a2.GeneratedFile(file_path=f"tests/step_defs/test_{STEM}.py", content=steps,
                             is_new_file=True, purpose="contract")]


def _gate(files):
    try:
        a2._validate_generated_files(files, "CONTRACT-1")
        return []
    except ValueError as e:
        return [str(e)]


def _m(sig, ret, body, doc="Answer one question about the page."):
    lines = "".join(f"        {b}\n" for b in body)
    return f"    def {sig} -> {ret}:\n        \"\"\"{doc}\"\"\"\n{lines}"


PLAIN = ('"the element answers the question"', "the element answers the question", "")
NAMED = ('parsers.parse(\'the entry "{name}" is listed\')', 'the entry "Alpha" is listed', ", name: str")
GONE = ('parsers.parse(\'the entry "{name}" is not listed\')', 'the entry "Alpha" is not listed', ", name: str")
COUNT = ("parsers.parse('there are {expected:d} entries')", "there are 2 entries", ", expected: int")
TEXT = ('parsers.parse(\'the element reads "{text}"\')', 'the element reads "Alpha"', ", text: str")


def _case(methods, step_line, kind):
    arg, phrase, params = kind
    return dict(methods=methods, step=step_line, arg=arg, phrase=phrase, params=params)


CANONICAL = {
    "presence check": _case(_m("is_element_shown(self)", "bool", [f"return self.is_showing({SEL})"]),
                            f"assert {FX}.is_element_shown(), \"Expected the element\"", PLAIN),
    "absence check": _case(_m("is_element_absent(self)", "bool", [f"return self.is_gone({SEL})"]),
                           f"assert {FX}.is_element_absent(), \"Expected no element\"", PLAIN),
    "readiness probe": _case(_m("is_loaded(self)", "bool", [f'return self.is_showing(self.sel("{READY}"))']),
                             f"assert {FX}.is_loaded(), \"Expected the page to load\"", PLAIN),
    "waiting reader": _case(_m("get_element_text(self)", "str",
                               [f"self.wait_visible({SEL})", f"return self.get_text({SEL})"],
                               doc="The element's text, once it is shown."),
                            f"assert {FX}.get_element_text() == text", TEXT),
    "entry listed": _case(_m("wait_until_listed(self, name: str)", "None",
                             [f"self.wait_for_row({FAM}, name, present=True)"],
                             doc="Wait until an entry containing `name` is listed."),
                          f"{FX}.wait_until_listed(name)", NAMED),
    "entry gone": _case(_m("wait_until_unlisted(self, name: str)", "None",
                           [f"self.wait_for_row({FAM}, name, present=False)"],
                           doc="Wait until no entry contains `name`."),
                        f"{FX}.wait_until_unlisted(name)", GONE),
    "exact count": _case(_m("assert_entry_count(self, expected: int)", "None",
                            [f"self.wait_for_count({FAM}, expected)"],
                            doc="Wait until exactly `expected` entries are listed."),
                         f"{FX}.assert_entry_count(expected)", COUNT),
    "act on one entry": _case(_m("open_entry(self, name: str)", "None",
                                 [f"self.click_in_row({FAM}, name, {CTRL})"],
                                 doc="Act on the entry containing `name`."),
                              f"{FX}.open_entry(name)", NAMED),
    "any entries": _case(_m("has_entries(self)", "bool",
                            [f"self.wait_for_any({FAM})", "return True"],
                            doc="True once at least one entry is listed."),
                         f"assert {FX}.has_entries(), \"Expected entries\"", PLAIN),
}


@pytest.fixture(autouse=True)
def _features_dir(tmp_path, monkeypatch):
    """The step file binds its feature by path; point that at a scratch dir."""
    import config.paths as paths
    (tmp_path / f"{STEM}.feature").write_text("Feature: x\n", encoding="utf-8")
    monkeypatch.setattr(paths, "FEATURES_DIR", tmp_path, raising=False)


def _run(c):
    return _gate(_batch(c["methods"], c["step"], c["phrase"], c["arg"], c["params"]))


def test_the_prompt_teaches_only_shapes_the_gate_accepts():
    """The generation prompt is the other voice. Each canonical call above
    must be what it teaches for absence - not a has_*() glance the predicate
    rule rejects for an unconditional element (rule 17 said exactly that
    until A3)."""
    text = (ROOT / "prompts" / "agent2_coder_generate.md").read_text(encoding="utf-8")
    assert "self.is_gone(" in text
    assert "Add a `has_<thing>()` helper next to the waiting getter" not in text


@pytest.mark.parametrize("concern", sorted(CANONICAL))
def test_the_canonical_answer_passes_the_whole_gate(concern, caplog):
    caplog.set_level("ERROR")
    errors = _run(CANONICAL[concern])
    assert errors == [], (
        f"the whole Agent 2 gate rejects the canonical {concern}: a model writing "
        f"the shape the prompt teaches would fail. A validator disagrees with the "
        f"others - fix the validator, not this test.\n{caplog.text[-1500:]}")


# (label, wrong case, the call the gate's message must name, the canonical fix)
REMEDIES = [
    ("absence by negated glance",
     _case(_m("is_element_absent(self)", "bool", [f"return not self.is_visible({SEL})"]),
           f"assert {FX}.is_element_absent()", PLAIN),
     "is_gone", "absence check"),
    ("presence by glance",
     _case(_m("is_element_shown(self)", "bool", [f"return self.is_visible({SEL})"]),
           f"assert {FX}.is_element_shown()", PLAIN),
     "is_showing", "presence check"),
    ("absence through a presence wait",
     _case(_m("is_element_shown(self)", "bool", [f"return self.is_showing({SEL})"]),
           f"assert not {FX}.is_element_shown()", PLAIN),
     "is_gone", "absence check"),
    ("any entries by snapshot count",
     _case(_m("has_entries(self)", "bool", [f"return self.get_count({FAM}) > 0"]),
           f"assert {FX}.has_entries()", PLAIN),
     "wait_for_any", "any entries"),
    ("clicking a whole family",
     _case(_m("open_entry(self, name: str)", "None", [f"self.click({FAM})"],
              doc="Act on the entry containing `name`."),
           f"{FX}.open_entry(name)", NAMED),
     "click_in_row", "act on one entry"),
]


@pytest.mark.parametrize("label,wrong,named,fix", REMEDIES, ids=[r[0] for r in REMEDIES])
def test_every_named_remedy_passes_the_whole_gate(label, wrong, named, fix, caplog):
    caplog.set_level("ERROR")
    errors = _run(wrong)
    assert errors, f"the gate let the wrong shape through: {label}"
    said = caplog.text + " ".join(errors)
    assert re.search(rf"\b{named}\b", said), (
        f"the gate rejected {label!r} but did not name {named}() as the fix:\n{said[-1200:]}")
    caplog.clear()
    assert _run(CANONICAL[fix]) == [], (
        f"the remedy the gate names for {label!r} is itself rejected by the gate - "
        f"the model would loop between two rules (validation story A3)\n{caplog.text[-1500:]}")
