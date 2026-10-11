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

from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[2]

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
import re
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
    step = _step("Detect runtime-affecting changes")
    assert step.get("id") == "changes", "the browser steps reference steps.changes"
    assert "github.event_name == 'push'" in str(step.get("if")), \
        "detection is meaningless on pull_request and dispatch, which always run the E2E"


def test_checkout_fetches_enough_history_to_diff():
    """`git diff <before> <sha>` needs the previous commit present. The default
    depth-1 clone does not have it."""
    checkout = _test_steps()[0]
    assert checkout.get("with", {}).get("fetch-depth") == 2


_BROWSER_STEPS = [
    "Cache Playwright browsers",
    "Install Playwright browsers",
    "Run app tests",
    "Upload test report",
]


@pytest.mark.parametrize("step_name", _BROWSER_STEPS)
def test_browser_steps_also_run_when_a_runtime_file_changed(step_name):
    cond = str(_step(step_name).get("if"))
    assert "steps.changes.outputs.inventory" in cond, (
        f"{step_name!r} still skips on every push. A runtime-file edit changes "
        f"what the existing E2E tests do, so it must run them."
    )


@pytest.mark.parametrize("step_name", _BROWSER_STEPS)
def test_browser_steps_fail_open(step_name):
    """`!= 'false'`, never `== 'true'`.

    With `== 'true'` there were only two ways to run the browser: the detector
    ran AND wrote 'true'. Every other outcome - crashed, skipped, empty output,
    a casing typo - evaluated false and SILENTLY skipped the E2E while the job
    went green reporting "all unit tests passed". An inventory change no
    browser had exercised, merged on a passing check.

    Only an explicit 'false' may skip. Over-running costs three minutes;
    under-running ships an untested change behind a green tick.
    """
    cond = str(_step(step_name).get("if"))
    assert "steps.changes.outputs.inventory != 'false'" in cond, (
        f"{step_name!r} uses a fail-CLOSED condition. A crashed or skipped "
        f"detector would silently downgrade the run to unit-only."
    )
    assert "outputs.inventory == 'true'" not in cond


def test_a_crashed_detector_cannot_fail_the_job():
    """The detector is advisory. If it dies the run must continue and the
    browser steps must fail open - not turn a diagnostic aid into a new way
    for the build to go red."""
    step = _step("Detect runtime-affecting changes")
    assert step.get("continue-on-error") is True


@pytest.mark.parametrize("output_value,should_run", [
    ("true",  True),   # detector ran, runtime file changed
    ("false", False),  # detector ran, nothing runtime changed - the ONLY skip
    ("",      True),   # detector crashed before writing the output
    (None,    True),   # step skipped entirely
    ("True",  True),   # casing drift in a future edit
])
def test_every_output_value_resolves_correctly(output_value, should_run):
    """Evaluates the real condition rather than trusting the string match."""
    cond = str(_step("Run app tests").get("if"))
    expr = (cond
            .replace("github.event_name != 'push'", "False")   # a push
            .replace("steps.changes.outputs.inventory != 'false'",
                     str(output_value != "false"))
            .replace("always()", "True")
            .replace("||", " or ").replace("&&", " and "))
    assert eval(expr) is should_run, (
        f"output {output_value!r} should {'run' if should_run else 'skip'} the E2E"
    )


def test_a_pull_request_always_runs_the_e2e():
    """The detector is push-only, so on a PR its output is empty. The event
    check must satisfy the condition on its own - otherwise an inventory change
    on a fix/ branch would skip the browser exactly where it matters most."""
    cond = str(_step("Run app tests").get("if"))
    expr = (cond
            .replace("github.event_name != 'push'", "True")
            .replace("steps.changes.outputs.inventory != 'false'", "True")
            .replace("always()", "True")
            .replace("||", " or ").replace("&&", " and "))
    assert eval(expr) is True


def test_detection_pattern_is_anchored_and_exact():
    """WIDENED from inventory-only to everything read at test runtime.

    Two properties still matter. The pattern must be anchored at ^, or a
    directory merely NAMED like a watched one would match. And filenames must
    be exact with escaped dots, so config/other.yaml and pages/listing_page.py
    - a generated file - are not swept in alongside config/config.yaml and
    pages/base_page.py.
    """
    run = str(_step("Detect runtime-affecting changes").get("run"))
    pattern = next((l.split("'")[1] for l in run.splitlines()
                    if l.strip().startswith("RUNTIME=")), None)
    assert pattern and pattern.startswith("^("), "the pattern must be anchored"
    assert r"config/config\.yaml" in pattern, "the dot must be escaped"
    assert not re.search(pattern, "config/other.yaml")
    assert not re.search(pattern, "pages/listing_page.py")
    assert not re.search(pattern, "app_inventory_old/x.json")


def test_detection_fails_safe_when_it_cannot_diff():
    """A first push to a branch has an all-zero before-SHA. Over-running the
    E2E wastes three minutes; skipping it silently ships an untested change."""
    run = str(_step("Detect runtime-affecting changes").get("run"))
    assert "0000000000000000000000000000000000000000" in run
    assert run.count("inventory=true") >= 3, \
        "each unusable-SHA branch must fall back to running the E2E"


# ─────────────────────────────────────────────────────────────────────────
# The E2E gate covers everything read AT TEST RUNTIME
#
# The criterion is not "is this an input to an agent" but "is this loaded when
# a test runs". Those overlap but differ in both directions: the two conftest
# files are not agent inputs yet ARE the entire E2E runtime, while prompts/ and
# core/app_context.py are agent inputs that no test ever reads.
# ─────────────────────────────────────────────────────────────────────────

_RUNTIME_FILES = [
    "app_inventory/any_app.json",              # BasePage.sel() resolves here
    "config/config.yaml",                      # base_url, timeouts, headless
    "pages/base_page.py",                      # every page object inherits it
    "tests/conftest.py",                       # browser + evidence capture
    "tests/step_defs/conftest.py",             # fixtures + credentials
]

_AGENT_ONLY_FILES = [
    "prompts/app_context/core.md",             # shapes generation, not a run
    "prompts/agent2_coder_generate.md",
    "core/app_context.py",                     # agents load it; tests do not
    "validators/method_resolution_validator.py",
]


@pytest.mark.parametrize("changed", _RUNTIME_FILES)
def test_runtime_files_are_in_the_push_paths(changed):
    """A file the E2E reads must at least trigger the workflow. Both conftest
    files triggered NOTHING before this - the entire fixture layer was
    ungated."""
    assert _fires(changed), f"{changed} triggers no workflow at all"


@pytest.mark.parametrize("changed", _RUNTIME_FILES)
def test_runtime_files_are_matched_by_the_e2e_detector(changed):
    """...and must also match the detector, or the workflow runs without the
    browser and the change ships unexercised."""
    run = str(_step("Detect runtime-affecting changes").get("run"))
    pattern = next((l.split("'")[1] for l in run.splitlines()
                    if l.strip().startswith("RUNTIME=")), None)
    assert pattern, "the RUNTIME pattern is missing from the detection step"
    assert re.search(pattern.replace("\\.", "\\."), changed), \
        f"{changed} is in the paths but the detector will not match it"


@pytest.mark.parametrize("changed", _AGENT_ONLY_FILES)
def test_agent_only_files_do_not_trigger_the_browser(changed):
    """Running a browser for a prompt edit costs three minutes and proves
    nothing: prompts shape what is GENERATED next time and cannot alter code
    that already exists."""
    run = str(_step("Detect runtime-affecting changes").get("run"))
    pattern = next((l.split("'")[1] for l in run.splitlines()
                    if l.strip().startswith("RUNTIME=")), None)
    assert pattern
    assert not re.search(pattern, changed), \
        f"{changed} would needlessly run the E2E"


def test_generated_step_defs_are_not_swept_in_wholesale():
    """tests/step_defs/** must NOT be a path: it holds Agent 2's generated step
    definitions, so merging a story PR would re-fire this gate on files Agent 4
    has already tested. Only the conftest is listed."""
    assert "tests/step_defs/**" not in _push_paths()
    assert "tests/step_defs/conftest.py" in _push_paths()
    assert not _fires("tests/step_defs/test_some_story.py")


# ─────────────────────────────────────────────────────────────────────────
# The summary must say WHY the E2E did or did not run
#
# A push with no runtime change legitimately skips the browser, but the
# summary read "All 635 tests passed" with no mention of it - inviting the
# reader to assume the app tests passed too. A green tick should not mean less
# than it appears to.
# ─────────────────────────────────────────────────────────────────────────

def _summary_step() -> dict:
    return _step("Write test summary")


def test_summary_receives_the_detector_verdict():
    """It cannot explain what it was never told."""
    env = _summary_step().get("env") or {}
    for key in ("E2E_EVENT", "E2E_DETECTOR", "E2E_DETECTOR_OUTCOME"):
        assert key in env, f"the summary step needs {key} to explain the E2E"


def test_summary_distinguishes_the_three_cases():
    """Skipped-by-design, detector-failed and no-verdict are different events
    and must not be conflated - the first is routine, the other two are not."""
    run = str(_summary_step().get("run"))
    assert "App E2E not run" in run, "no note for a legitimately skipped E2E"
    assert "change detector failed" in run, "no note for a crashed detector"
    assert "produced no verdict" in run, "no note for a missing verdict"


def test_summary_names_the_files_that_trigger_the_browser():
    """A reader who sees 'E2E not run' should not have to hunt for the rule."""
    run = str(_summary_step().get("run"))
    for f in ("app_inventory/", "config/config.yaml", "pages/base_page.py", "conftest.py"):
        assert f in run, f"the skip note should name {f}"


def test_the_note_is_push_only():
    """On a pull request and a manual dispatch the E2E always runs, so a note
    would be noise."""
    run = str(_summary_step().get("run"))
    assert 'event == "push"' in run

# ─────────────────────────────────────────────────────────────────────────
# CLI scripts must not reference undefined names
#
# verify_locators.py used `logger.info(...)` in a module that has no logger
# and prints everywhere else. It raised NameError on the FIRST line of real
# work, for anyone who did not pass --login-url - which the previous change
# had just made the normal case. check_inventory_staleness.py had the same
# bug from the same edit. Neither is exercised by any unit test, because both
# need a browser, so nothing caught it.
#
# This does not run the scripts. It walks their AST and asserts every name
# they LOAD is one they define, import, or take as an argument.
# ─────────────────────────────────────────────────────────────────────────
import ast
import builtins


def _undefined_names(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    defined = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            defined.add(n.id)
        elif isinstance(n, ast.arg):
            defined.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            defined.add(n.name)
        elif isinstance(n, ast.Global):
            defined.update(n.names)
    used = {n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return sorted(used - defined)


@pytest.mark.parametrize("script", [
    "scripts/verify_locators.py",
    "scripts/check_inventory_staleness.py",
    "scripts/generate_inventory.py",
    "scripts/promote_draft.py",
])
def test_cli_scripts_reference_only_defined_names(script):
    path = _repo_root() / script
    if not path.is_file():
        pytest.skip(f"{script} is not present in this checkout")
    missing = _undefined_names(path)
    assert not missing, (
        f"{script} loads names it never defines: {missing}. These scripts need "
        f"a browser, so no unit test executes them - a NameError here only "
        f"surfaces when someone runs the tool."
    )

# ─────────────────────────────────────────────────────────────────────────
# The draft carries its own review checklist
#
# A generated inventory is not committable: components, elements_notes and
# key_methods are empty by construction, and several review blocks must be
# acted on and removed. Keeping that checklist only in the guide meant the
# person editing the file had to remember it was there.
# ─────────────────────────────────────────────────────────────────────────

def _conventions_source() -> str:
    return (_repo_root() / "scripts" / "generate_inventory.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("step", [
    "1_WRITE", "2_VERIFY_AND_CORRECT_never_delete",
    "3_FIX_THEN_DELETE_THE_BLOCK", "4_DELETE_OUTRIGHT", "5_THEN_MEASURE",
])
def test_the_checklist_has_all_five_stages(step):
    assert step in _conventions_source()


@pytest.mark.parametrize("key", [
    "components", "elements_notes", "key_methods", "errors",
    "url + url_sample", "always",
    "multi_match", "conditional",
    "_selectors_to_improve", "_families_without_a_shared_handle",
    "_third_party_elements", "_unresolved_selectors",
    "implementation_status", "title_seen",
])
def test_every_field_a_draft_carries_is_in_the_checklist(key):
    """A field the crawler emits but the checklist omits is a field someone
    will leave half-reviewed."""
    assert key in _conventions_source(), f"{key} is not covered by the checklist"


def test_the_enforced_fields_are_marked_verify_not_delete():
    """multi_match is what rejects generated code that clicks a family; deleting
    it removes that protection silently. conditional reaches Agent 2 and stops
    verify_locators reporting those keys as faults. Neither is a review
    artefact, and the checklist must not read as though they are."""
    src = _conventions_source()
    verify_block = src[src.index("2_VERIFY_AND_CORRECT_never_delete"):
                       src.index("3_FIX_THEN_DELETE_THE_BLOCK")]
    assert "multi_match" in verify_block
    assert "conditional" in verify_block
    delete_block = src[src.index("4_DELETE_OUTRIGHT"):src.index("5_THEN_MEASURE")]
    assert "multi_match" not in delete_block
    assert '"conditional"' not in delete_block


# =========================================================================
# EVERYTHING THE REPAIR LOOP FINDS, THE GATE MUST BE ABLE TO STOP
#
# Six checks lived only in _collect_repairable_errors. They were detected,
# fed to the repair loop, and when four attempts failed the loop logged
#
#     "Validator repair exhausted 4 retry attempt(s); N error(s) remain.
#      Final validator will raise."
#
# and returned the files. The final validator did not run them. Nothing
# raised. The pull request opened carrying the defect the framework had
# already named, in the exact words it would have used to reject it.
#
# The log line was not a lie anyone wrote deliberately - it was true when the
# repairable set and the gate held the same checks, and stopped being true
# each time one was added to the loop and not the gate. Six times.
#
# A detected-but-unenforced check is worse than no check: it costs four LLM
# calls, prints a warning nobody reads, and ships anyway.
# =========================================================================

def _a_real_inventory_page() -> str:
    """A page name the inventory actually declares.

    Discovered, not named: which pages exist is the application's business,
    and hardcoding one would put app knowledge in a framework test.
    """
    import json

    import yaml

    config = yaml.safe_load(
        (_ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    rel = (config.get("app_under_test") or {}).get("inventory_file")
    inventory = json.loads((_ROOT / rel).read_text(encoding="utf-8"))
    return next(iter(inventory.get("pages") or {}), "")


def _page_object_with(method: str) -> "SimpleNamespace":
    from types import SimpleNamespace
    page = _a_real_inventory_page()
    return SimpleNamespace(
        file_path="pages/widget_page.py", is_new_file=True,
        content=('"""Widget page object."""\n'
                 "from pages.base_page import BasePage\n\n\n"
                 "class WidgetPage(BasePage):\n"
                 f'    INVENTORY_PAGE = "{page}"\n\n'
                 f"    def {method}(self, base_url: str) -> None:\n"
                 "        self.navigate(base_url)\n"),
    )


def test_every_repairable_check_can_stop_a_pull_request():
    """The gate must raise on anything the repair loop can still find.

    `open()` is a bare verb - rejected by validate_page_object_methods, which
    lives ONLY in the repairable set. Nothing in the gate's own nine checks
    objects to this file, so if the gate stays silent the pull request opens
    carrying a defect the framework already named.
    """
    from agents.agent2_coder import _collect_repairable_errors, _validate_generated_files

    batch = [_page_object_with("open")]
    if not _a_real_inventory_page():
        pytest.skip("no inventory in this checkout")

    assert _collect_repairable_errors(batch), (
        "the sample batch is clean - this test would pass vacuously"
    )

    with pytest.raises(ValueError) as excinfo:
        _validate_generated_files(batch, "STORY-1")
    assert "STORY-1" in str(excinfo.value), "name the story that was stopped"


def test_a_clean_batch_still_passes_the_gate():
    """Break the thing the guard guards.

    A backstop that raised on everything would stop every story. The same file
    with a method that says what it opens must pass.
    """
    from agents.agent2_coder import _collect_repairable_errors, _validate_generated_files

    batch = [_page_object_with("open_widget")]
    if not _a_real_inventory_page():
        pytest.skip("no inventory in this checkout")

    assert _collect_repairable_errors(batch) == [], (
        "the sample is not clean; adjust it rather than weakening the gate"
    )
    _validate_generated_files(batch, "STORY-2")   # must not raise


def test_the_row_scope_check_is_wired_into_the_gate():
    """A validator nothing calls is this project's recurring shape.

    The check itself passed its own tests while being unreachable from the
    pipeline - removing the call site changed nothing, which is exactly the
    failure mode `dismiss_interstitial` had for months.
    """
    source = (_ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    body = " ".join(source.split())

    assert "validate_row_scoped_selectors(generated_files, PROJECT_ROOT)" in body, (
        "the row-scope validator is defined but never called - a cell "
        "selector anchored above its row would ship again"
    )