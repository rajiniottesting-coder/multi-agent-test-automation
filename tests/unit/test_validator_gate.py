"""Tests for the Agent 2 validator gate and batch-aware fixture derivation.

Three production defects are pinned here:

  1. A page object generated in the same batch was reported as a missing
     fixture. No repair attempt could satisfy it, so it consumed the whole
     retry budget while the file providing it was being written.
  2. validate_no_unused_step_definitions and validate_fixtures_exist fed the
     repair loop but not the final gate, so a run could log "Final validator
     will raise", exhaust its retries, and open a PR carrying those errors.
  3. Scan mode printed [FAIL] for a story and exited 0.
"""
import inspect

import pytest

import agents.agent2_coder as agent2
from validators.gherkin_analyzer import validate_fixtures_exist


class _GF:
    def __init__(self, file_path: str, content: str):
        self.file_path = file_path
        self.content = content


_PAGE_OBJECT = (
    "from pages.base_page import BasePage\n\n\n"
    "class WidgetPage(BasePage):\n    pass\n"
)


def _step_def(*fixtures: str) -> str:
    return (
        "from pytest_bdd import given\n\n\n"
        '@given("I am somewhere")\n'
        f"def go({', '.join(fixtures)}) -> None:\n    pass\n"
    )


# ── defect 1: batch-aware derivation ─────────────────────────────────────

def test_page_object_generated_in_the_same_batch_is_accepted():
    """The false positive that burned four repair attempts in production."""
    files = [
        _GF("pages/widget_page.py", _PAGE_OBJECT),
        _GF("tests/step_defs/test_x.py", _step_def("widget_page")),
    ]
    assert validate_fixtures_exist(files, ".") == []


def test_fixture_with_no_page_object_anywhere_is_still_caught():
    """The genuine bug must not be masked by the fix for the false positive."""
    files = [
        _GF("pages/widget_page.py", _PAGE_OBJECT),
        _GF("tests/step_defs/test_x.py", _step_def("nowhere_page")),
    ]
    errors = validate_fixtures_exist(files, ".")
    assert len(errors) == 1 and "nowhere_page" in errors[0]


def test_generated_page_object_that_does_not_parse_is_not_trusted():
    """conftest imports page objects; an unparseable one registers nothing."""
    files = [
        _GF("pages/broken_page.py", "class BrokenPage(BasePage:\n bad\n"),
        _GF("tests/step_defs/test_x.py", _step_def("broken_page")),
    ]
    assert len(validate_fixtures_exist(files, ".")) == 1


def test_generated_non_page_class_is_not_trusted():
    files = [
        _GF("pages/helper.py", "class Helper:\n    pass\n"),
        _GF("tests/step_defs/test_x.py", _step_def("helper")),
    ]
    assert len(validate_fixtures_exist(files, ".")) == 1


def test_generated_file_outside_pages_is_not_trusted():
    """Only pages/ is auto-registered, so only pages/ may be trusted."""
    files = [
        _GF("utils/widget_page.py", _PAGE_OBJECT),
        _GF("tests/step_defs/test_x.py", _step_def("widget_page")),
    ]
    assert len(validate_fixtures_exist(files, ".")) == 1


def test_generated_class_named_page_is_refused():
    """Would derive 'page' and shadow the browser fixture."""
    files = [
        _GF("pages/page.py",
            "from pages.base_page import BasePage\n\n\nclass Page(BasePage):\n    pass\n"),
        _GF("tests/step_defs/test_x.py", _step_def("something_page")),
    ]
    assert len(validate_fixtures_exist(files, ".")) == 1


# ── defect 2: the final gate must be able to block ───────────────────────

_FEATURE = "Feature: f\n\n  Scenario: s\n    Given I am somewhere\n"


def test_gate_blocks_an_unresolvable_fixture():
    files = [
        _GF("features/x.feature", _FEATURE),
        _GF("tests/step_defs/test_x.py", _step_def("nowhere_page")),
    ]
    with pytest.raises(ValueError, match="Fixture resolution validation failed"):
        agent2._validate_generated_files(files, "STORY-1")


def test_gate_blocks_an_unused_step_definition():
    step_def = _step_def("login_page") + (
        '\n\n@given("nothing uses this")\n'
        "def dead(login_page) -> None:\n    pass\n"
    )
    files = [
        _GF("features/x.feature", _FEATURE),
        _GF("tests/step_defs/test_x.py", step_def),
    ]
    with pytest.raises(ValueError, match="Unused step-definition validation failed"):
        agent2._validate_generated_files(files, "STORY-1")


def test_gate_passes_a_clean_batch():
    """The gate must not become a false blocker."""
    files = [
        _GF("features/x.feature", _FEATURE),
        _GF("tests/step_defs/test_x.py", _step_def("widget_page")),
        _GF("pages/widget_page.py", _PAGE_OBJECT),
    ]
    agent2._validate_generated_files(files, "STORY-1")      # must not raise


def test_both_new_validators_are_wired_into_the_gate():
    """Guards against either being dropped back to repair-loop-only."""
    src = inspect.getsource(agent2._validate_generated_files)
    assert "validate_no_unused_step_definitions" in src
    assert "validate_fixtures_exist" in src


def test_selector_validator_is_wired_into_the_gate():
    """SCRUM-104: the no-literal-selectors rule lived only in
    tests/unit/test_page_object_selectors.py, so it was enforced in Agent 4 —
    after the tokens were spent and the PR was open. If this assertion ever
    fails, that regression is back.
    """
    src = inspect.getsource(agent2._validate_generated_files)
    assert "validate_page_object_selectors" in src


# ── defect 3: scan mode must signal failure ──────────────────────────────

def test_scan_mode_exits_non_zero_when_a_story_failed():
    src = inspect.getsource(agent2.main)
    assert 'r.get("status") == "failed"' in src
    assert "sys.exit(1)" in src


def test_system_exit_is_re_raised_before_the_broad_handler():
    """Otherwise our own exit(1) is caught and reported as a crash."""
    import ast
    tree = ast.parse(inspect.getsource(agent2.main))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        names = ["bare" if h.type is None else ast.unparse(h.type)
                 for h in node.handlers]
        if "SystemExit" in names:
            assert names.index("SystemExit") < names.index("Exception")
            return
    pytest.fail("no try block re-raises SystemExit")

# ─────────────────────────────────────────────────────────────────────────
# CI gate coverage
#
# The unit suite is only worth anything if it actually RUNS when the thing it
# validates changes. app_inventory/ and prompts/ were missing from the push
# paths, so an inventory edit triggered no workflow at all - not "ran and
# passed", but never ran - and a renamed key surfaced during a story run
# instead of in 90 seconds. These lock that shut.
# ─────────────────────────────────────────────────────────────────────────
import fnmatch
from pathlib import Path

import yaml


def _repo_root():
    return Path(__file__).resolve().parents[2]


def _push_paths() -> list:
    wf = yaml.safe_load(
        (_repo_root() / ".github" / "workflows" / "agent4_runner.yml")
        .read_text(encoding="utf-8")
    )
    # PyYAML parses the bare key `on:` as the boolean True.
    triggers = wf.get(True) or wf.get("on") or {}
    return (triggers.get("push") or {}).get("paths") or []


def _fires(path: str) -> bool:
    return any(
        fnmatch.fnmatch(path, pat) or (pat.endswith("/**") and path.startswith(pat[:-2]))
        for pat in _push_paths()
    )


class TestPushGateCoversWhatTheSuiteValidates:

    @pytest.mark.parametrize("changed", [
        "app_inventory/anything.json",
        "prompts/agent2_coder_generate.md",
        "prompts/app_context/core.md",
        "core/failure_diagnosis.py",
        "validators/method_resolution_validator.py",
        "inventory_tools/introspect.py",
        "pages/base_page.py",
        "tests/unit/test_validators.py",
    ])
    def test_framework_changes_trigger_the_gate(self, changed):
        assert _fires(changed), (
            f"{changed} changes nothing in CI. The suite validates it, so a "
            f"break there would ship silently."
        )

    @pytest.mark.parametrize("changed", [
        "features/some_story.feature",
        "tests/step_defs/test_some_story.py",
        "pages/some_story_page.py",
        "README.md",
        "docs/GUIDE.md",
    ])
    def test_generated_and_doc_files_do_not_trigger_it(self, changed):
        """Agent-generated files must NOT be in the push paths: merging a story
        PR would otherwise re-fire the framework gate on files Agent 4 has
        already tested. pages/base_page.py is listed individually for exactly
        this reason - it is reserved, the generated page objects are not."""
        assert not _fires(changed), f"{changed} should not trigger the framework gate"


def test_inventory_health_workflow_is_wired():
    """The nightly DOM check is the only thing that proves a selector RESOLVES.
    If it stops being scheduled, that class of failure goes back to surfacing
    mid-story."""
    wf_path = _repo_root() / ".github" / "workflows" / "inventory_health.yml"
    assert wf_path.is_file(), "the nightly inventory check is missing"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    triggers = wf.get(True) or wf.get("on") or {}
    assert "schedule" in triggers, "inventory health must run on a schedule"
    assert "workflow_dispatch" in triggers, "it must also be runnable on demand"
    steps = wf["jobs"]["verify"]["steps"]
    assert any("verify_locators" in str(s.get("run", "")) for s in steps), \
        "it must actually call verify_locators"


def test_inventory_health_does_not_hardcode_the_login_path():
    """The login page is recorded in the inventory, so the workflow must not
    repeat it. A workflow that duplicates inventory data is one that drifts
    from it - and the flag only existed to paper over a wrong default."""
    wf_path = _repo_root() / ".github" / "workflows" / "inventory_health.yml"
    verify = [s for s in yaml.safe_load(wf_path.read_text(encoding="utf-8"))
              ["jobs"]["verify"]["steps"] if s.get("id") == "verify"][0]
    run = str(verify.get("run", ""))
    # strip comment lines before asserting - the comment explains the absence
    code = "\n".join(l for l in run.splitlines() if not l.strip().startswith("#"))
    assert "--login-url" not in code, \
        "the login path should come from the inventory, not this workflow"


def test_inventory_health_lists_no_pages():
    """Scope is 'every page in the configured inventory'. A page list here
    would silently fall behind as the app grows."""
    wf_path = _repo_root() / ".github" / "workflows" / "inventory_health.yml"
    wf = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    inputs = (wf.get(True) or wf.get("on"))["workflow_dispatch"].get("inputs") or {}
    assert set(inputs) == {"page"}, \
        f"unexpected dispatch inputs: {sorted(inputs)}"
    assert (inputs["page"].get("default") or "") == "", \
        "the default must be blank so the scheduled run sweeps every page"


def test_login_path_comes_from_the_inventory():
    """find_login_path must locate the login page in whatever app is
    configured, without naming any application."""
    import json
    from inventory_tools.browser import find_login_path
    from core.app_context import AppContext
    ctx = AppContext.load()
    inv = json.loads(Path(ctx.inventory_path()).read_text(encoding="utf-8"))
    assert find_login_path(inv), (
        "no login page found in the configured inventory - the browser tools "
        "would fall back to '/' and fail to sign in on any app whose root is "
        "not a login screen"
    )

# ─────────────────────────────────────────────────────────────────────────
# Inventory pushes must run the E2E
#
# Page objects hold no selectors - they call self.sel("key") and BasePage reads
# the inventory AT RUNTIME. So an inventory edit changes what every existing
# E2E test does, with no code change at all. On a push only the unit suite ran,
# which proves the inventory is structurally sound and nothing about whether
# the tests still pass against it.
# ─────────────────────────────────────────────────────────────────────────

def _agent4() -> dict:
    return yaml.safe_load(
        (_repo_root() / ".github" / "workflows" / "agent4_runner.yml")
        .read_text(encoding="utf-8")
    )


def _test_steps() -> list:
    return _agent4()["jobs"]["test"]["steps"]


def _step(name_fragment: str) -> dict:
    for s in _test_steps():
        if name_fragment.lower() in (s.get("name") or "").lower():
            return s
    raise AssertionError(f"no step matching {name_fragment!r}")


def test_the_detection_step_exists_and_is_push_only():
    step = _step("Detect inventory changes")
    assert step.get("id") == "changes", "the browser steps reference steps.changes"
    assert "github.event_name == 'push'" in str(step.get("if")), \
        "detection is meaningless on pull_request and dispatch, which always run the E2E"


def test_checkout_fetches_enough_history_to_diff():
    """`git diff <before> <sha>` needs the previous commit present. The default
    depth-1 clone does not have it."""
    checkout = _test_steps()[0]
    assert checkout.get("with", {}).get("fetch-depth") == 2


@pytest.mark.parametrize("step_name", [
    "Cache Playwright browsers",
    "Install Playwright browsers",
    "Run app tests",
    "Upload test report",
])
def test_browser_steps_also_run_when_the_inventory_changed(step_name):
    cond = str(_step(step_name).get("if"))
    assert "steps.changes.outputs.inventory == 'true'" in cond, (
        f"{step_name!r} still skips on every push. An inventory edit changes "
        f"what the existing E2E tests do, so it must run them."
    )


def test_detection_matches_only_the_inventory_directory():
    """prompts/ must NOT trigger the E2E: it shapes what the agents GENERATE
    next time, and cannot alter code that already exists. And the pattern must
    be anchored, or a directory merely named similarly would match."""
    run = str(_step("Detect inventory changes").get("run"))
    assert "'^app_inventory/'" in run, "the grep pattern must be anchored at ^"
    assert "prompts/" not in run, "a prompt change must not trigger the browser"


def test_detection_fails_safe_when_it_cannot_diff():
    """A first push to a branch has an all-zero before-SHA. Over-running the
    E2E wastes three minutes; skipping it silently ships an untested change."""
    run = str(_step("Detect inventory changes").get("run"))
    assert "0000000000000000000000000000000000000000" in run
    assert run.count("inventory=true") >= 3, \
        "each unusable-SHA branch must fall back to running the E2E"