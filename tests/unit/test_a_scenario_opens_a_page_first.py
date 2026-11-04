"""A scenario opens a page before it acts on one.

4 Nov 2026: a generated Background clicked a top-menu link as
its first move - the test case said "open the home page, then click the
link", and "open" was lost. Every test starts on the browser's empty page, so
both scenarios waited 30 seconds for a link that could never appear, and the
failure blamed the selector. Agent 3 then blocked the pull request over the
menu method "possibly not existing" - it was on main, outside the diff.

Three guards: Agent 2's check (validators/opening_step.py), BasePage refusing
an action on the empty starting page with a message that names the cause, and
Agent 3 shown the page-object methods the step definitions call. Generic names.
"""
import os
from pathlib import Path

import pytest

from core.schemas import GeneratedFile
from validators.opening_step import validate_scenarios_open_a_page_first

ROOT = Path(__file__).resolve().parents[2]

MENU = '''from pages.base_page import BasePage


class TopMenuPage(BasePage):
    INVENTORY_PAGE = "top_menu"

    def go_to_help(self) -> None:
        """Open the help page from the menu."""
        self.click(self.sel("help_link"))
'''
START = '''from pages.base_page import BasePage


class StartPage(BasePage):
    INVENTORY_PAGE = "start"

    def open_start(self, base_url: str) -> None:
        """Open the start page."""
        self.navigate(base_url)

    def open_start_via_helper(self, base_url: str) -> None:
        """Open it through another method of the class."""
        self.open_start(base_url)

    def is_loaded(self) -> bool:
        return self.is_showing(self.sel("banner"))
'''
FEATURE = '''Feature: Help

  Background:
    Given I am on the help page

  Scenario: Reading help
    Then the help should be shown

  Scenario: Reading help again
    Then the help should be shown
'''


def _steps(given_body: str) -> str:
    return f'''from pytest_bdd import given, then, scenarios

scenarios("help.feature")


@given("I am on the help page")
def on_help(top_menu_page, start_page, base_url):
{given_body}


@then("the help should be shown")
def help_shown(start_page):
    assert start_page.is_loaded()
'''


def _files(given_body, feature=FEATURE):
    return [GeneratedFile(file_path="features/help.feature", content=feature),
            GeneratedFile(file_path="tests/step_defs/test_help.py", content=_steps(given_body)),
            GeneratedFile(file_path="pages/top_menu_page.py", content=MENU),
            GeneratedFile(file_path="pages/start_page.py", content=START)]


# ── Agent 2's check ─────────────────────────────────────────────────────

def test_a_first_step_that_clicks_before_opening_is_refused_once(tmp_path):
    errors = validate_scenarios_open_a_page_first(
        _files("    top_menu_page.go_to_help()"), tmp_path)
    assert len(errors) == 1, "the Background is shared: one error, not one per scenario"
    e = errors[0]
    assert e.startswith("Opening step error in 'tests/step_defs/test_help.py'")
    assert "`Given I am on the help page`" in e and "top_menu_page.go_to_help()" in e
    assert "navigate()" in e


@pytest.mark.parametrize("body", [
    "    start_page.open_start(base_url)\n    top_menu_page.go_to_help()",
    "    start_page.open_start_via_helper(base_url)\n    top_menu_page.go_to_help()",
])
def test_opening_first_passes(tmp_path, body):
    assert validate_scenarios_open_a_page_first(_files(body), tmp_path) == []


@pytest.mark.parametrize("body", [
    "    pass",                                          # a fixture does the work
    "    top_menu_page.unknown_method()",                # not on the class: unknown
    "    helper_thing.go()",                             # not a page object
])
def test_what_cannot_be_read_is_left_alone(tmp_path, body):
    assert validate_scenarios_open_a_page_first(_files(body), tmp_path) == []


def test_without_a_background_each_scenario_s_own_first_step_counts(tmp_path):
    feature = FEATURE.replace("  Background:\n    Given I am on the help page\n\n", "").replace(
        "    Then the help should be shown\n", "    Given I am on the help page\n"
        "    Then the help should be shown\n")
    errors = validate_scenarios_open_a_page_first(
        _files("    top_menu_page.go_to_help()", feature), tmp_path)
    assert len(errors) == 1, "the same step is reported once"


def test_a_scenario_that_opens_on_a_check_is_not_judged(tmp_path):
    feature = FEATURE.replace("  Background:\n    Given I am on the help page\n\n", "")
    steps = _steps("    top_menu_page.go_to_help()").replace(
        "def help_shown(start_page):\n    assert start_page.is_loaded()",
        "def help_shown(top_menu_page):\n    top_menu_page.go_to_help()")
    assert "def help_shown(top_menu_page)" in steps
    files = _files("    pass", feature)
    files[1] = GeneratedFile(file_path="tests/step_defs/test_help.py", content=steps)
    assert validate_scenarios_open_a_page_first(files, tmp_path) == []


def test_every_feature_on_main_already_opens_a_page_first():
    files = []
    for feature in sorted((ROOT / "features").glob("*.feature")):
        files.append(GeneratedFile(file_path=f"features/{feature.name}",
                                   content=feature.read_text(encoding="utf-8")))
        steps = ROOT / "tests" / "step_defs" / f"test_{feature.stem}.py"
        if steps.exists():
            files.append(GeneratedFile(file_path=f"tests/step_defs/{steps.name}",
                                       content=steps.read_text(encoding="utf-8")))
    assert files and validate_scenarios_open_a_page_first(files, ROOT) == []


def test_agent2_runs_it_with_its_other_checks():
    src = (ROOT / "agents" / "agent2_coder.py").read_text(encoding="utf-8")
    body = src.split("def _collect_repairable_errors(", 1)[1].split("\ndef ", 1)[0]
    assert "validate_scenarios_open_a_page_first(generated_files, PROJECT_ROOT)" in body


# ── BasePage refuses the empty starting page ─────────────────────────────

def test_the_diagnosis_names_the_cause():
    from core.failure_diagnosis import diagnose
    d = diagnose("AssertionError: No page is open (the browser is still on its empty "
                 "starting page): the scenario's first step must open a page - ...")
    assert d.label == "no page opened before acting"


@pytest.fixture(scope="module")
def browser():
    sync = pytest.importorskip("playwright.sync_api")
    pw = sync.sync_playwright().start()
    exe = os.getenv("CHROMIUM_EXECUTABLE")
    try:
        b = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
    except Exception as e:                                         # noqa: BLE001
        pw.stop()
        pytest.skip(f"no browser: {e}")
    yield b
    b.close()
    pw.stop()


def _page_object(page):
    from pages.base_page import BasePage
    obj = BasePage.__new__(BasePage)
    obj.page = page
    return obj


def test_an_action_on_the_empty_starting_page_fails_at_once(browser):
    import time
    page = browser.new_page()
    page.set_default_timeout(30000)
    start = time.monotonic()
    with pytest.raises(AssertionError, match="No page is open"):
        _page_object(page).click("a[href='/help']")
    assert time.monotonic() - start < 5, "not the 30-second wait for a selector"
    page.close()


def test_a_page_a_test_filled_itself_is_acted_on_as_before(browser):
    page = browser.new_page()
    page.set_content("<button id='b' onclick=\"this.textContent='done'\">go</button>")
    _page_object(page).click("#b")
    assert page.text_content("#b") == "done"
    page.close()


# ── Agent 3 sees the methods that already exist ──────────────────────────

def _changed(steps, pages=()):
    return ([{"filename": "tests/step_defs/test_help.py", "content": steps}]
            + [{"filename": p, "content": c} for p, c in pages])


def test_agent3_is_shown_a_method_on_main_outside_the_diff(tmp_path):
    from agents.agent3_reviewer import page_object_methods_called
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "top_menu_page.py").write_text(MENU)
    text = page_object_methods_called(_changed(_steps("    top_menu_page.go_to_help()")), tmp_path)
    assert "`TopMenuPage.go_to_help() -> None` - Open the help page from the menu." in text
    assert "EXIST" in text and "Never report one of them as missing" in text


def test_the_pull_requests_version_wins_and_inherited_ones_are_left_to_agent2(tmp_path):
    from agents.agent3_reviewer import page_object_methods_called
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "start_page.py").write_text("class StartPage:\n    pass\n")
    steps = _steps("    start_page.open_start(base_url)\n    start_page.wait_visible('x')")
    text = page_object_methods_called(_changed(steps, [("pages/start_page.py", START)]), tmp_path)
    assert "StartPage.open_start(base_url: str) -> None" in text
    assert "wait_visible" not in text, "a BasePage helper is not shown as a page method"


def test_no_call_means_no_section(tmp_path):
    from agents.agent3_reviewer import page_object_methods_called
    assert page_object_methods_called(_changed("x = 1\n"), tmp_path) == ""


def test_the_review_prompt_carries_the_section():
    prompt = (ROOT / "prompts" / "agent3_reviewer.md").read_text(encoding="utf-8")
    src = (ROOT / "agents" / "agent3_reviewer.py").read_text(encoding="utf-8")
    assert "{page_object_methods_section}" in prompt
    assert '.replace("{page_object_methods_section}",' in src
