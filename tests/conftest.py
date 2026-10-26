"""
Pytest fixtures shared across all tests.
The `page` fixture provides a fresh Playwright Browser tab for each scenario.
"""
import logging
import os
import yaml
import pytest
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, Page, Browser
from dotenv import load_dotenv
from config.paths import CONFIG_YAML

load_dotenv()

logger = logging.getLogger(__name__)


def load_config():
    """Load YAML config once."""
    with open(CONFIG_YAML) as f:
        return yaml.safe_load(f)


def is_headless_mode(config_value: bool) -> bool:
    """Decide whether Playwright should run headless.

    Priority:
      1. PLAYWRIGHT_HEADLESS env var (explicit override) — set to "true" / "false"
      2. CI env var (auto-set by GitHub Actions, GitLab CI, Jenkins, etc.) → headless
      3. config.yaml `browser.headless` value (the default for local dev)

    This lets you keep `headless: false` in config.yaml for local dev
    (so you can SEE what's happening), while CI always runs headless
    (where there's no display).
    """
    # Explicit override always wins
    explicit = os.getenv("PLAYWRIGHT_HEADLESS")
    if explicit is not None:
        return explicit.lower() in ("true", "1", "yes")

    # CI environments auto-set CI=true
    if os.getenv("CI", "").lower() == "true":
        return True

    # Fall back to config
    return config_value


def should_block_request(url: str, blocked_hosts) -> bool:
    """True if `url`'s host ends with one of `blocked_hosts`.

    Suffix matching, so one entry covers a whole network's subdomains -
    `pagead2.x.com` and `tpc.x.com` both match `x.com`. Anchored on a dot
    boundary as well as the bare host, so a suffix can never match a
    DIFFERENT domain that merely ends with the same letters.

    Pure and browser-free on purpose: the routing rule is the part worth
    testing, and a test that needs a real browser to check a string comparison
    does not get written.
    """
    if not blocked_hosts:
        return False
    try:
        host = urlsplit(url).hostname or ""
    except Exception:                                     # noqa: BLE001
        return False
    host = host.lower()
    for blocked in blocked_hosts:
        blocked = str(blocked).lower().lstrip(".")
        if host == blocked or host.endswith("." + blocked):
            return True
    return False


def pytest_configure(config):
    """Fill the Allure report's metadata panels before any test runs.

    ENVIRONMENT, CATEGORIES, EXECUTORS and TREND are all blank unless
    something writes them, and none is a by-product of running tests. A
    report with four empty boxes reads as a report that does not work.

    Done here rather than in a fixture because the files must exist before
    the first result is written, and `pytest_configure` is the earliest hook
    that knows where --alluredir points.

    Everything written is DERIVED - from config.yaml, from the environment,
    and from the framework's own diagnosis signatures - so pointing at a
    different application changes every value without changing this code.
    """
    results_dir = config.getoption("--alluredir", default=None)
    if not results_dir:
        return                                    # not an Allure run

    try:
        from core.allure_meta import write_allure_metadata

        written = write_allure_metadata(results_dir,
                                        project_root=Path(__file__).resolve().parents[1])
        if written:
            logger.info(
                "Allure metadata: %s environment value(s), %s categor(ies), "
                "executor recorded, trend history %s",
                written.get("environment", 0), written.get("categories", 0),
                "carried forward" if written.get("history") else
                "not available (first run, or no previous report)",
            )
    except Exception:                                     # noqa: BLE001
        # Never fail a session over report decoration.
        logger.debug("Allure metadata not written", exc_info=True)


@pytest.fixture(scope="session")
def config():
    """Provide test config to any test that needs it."""
    return load_config()


@pytest.fixture(scope="session")
def base_url(config) -> str:
    """The application base URL — single source of truth.

    Priority:
      1. BASE_URL env var (explicit override — useful for pointing tests at
         dev/staging/prod without changing config.yaml)
      2. config.yaml `base_url` (the default for local dev)

    Page objects receive this via their open() method, so the URL is never
    hardcoded in pages/ or tests/.
    """
    return os.getenv("BASE_URL") or config["base_url"]


@pytest.fixture(scope="session")
def playwright_instance():
    """One Playwright instance for the whole test run."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance, config) -> Browser:
    """One browser instance per session (faster than one-per-test)."""
    browser_config = config["browser"]
    headless = is_headless_mode(browser_config["headless"])
    # In CI, slow_mo=0 (no need to slow down for visual debugging)
    slow_mo = 0 if headless else browser_config["slow_mo"]

    browser = playwright_instance.chromium.launch(
        headless=headless,
        slow_mo=slow_mo,
    )
    yield browser
    browser.close()


@pytest.fixture
def page(browser, config, request) -> Page:
    """Fresh browser tab (context) for each test — full isolation.

    On test FAILURE, captures three artifacts into reports/failure-evidence/:
      - <test>.png    a screenshot of the final page state
      - <test>.webm   a video recording of the whole test
      - <test>.zip    a Playwright trace (open with `playwright show-trace`)
    On pass, nothing is written (video/trace are discarded) to keep artifact
    size down. Requires the pytest_runtest_makereport hook below to know the
    outcome.
    """
    from pathlib import Path as _Path
    evidence_dir = _Path("reports/failure-evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    browser_config = config["browser"]
    context = browser.new_context(
        viewport=browser_config["viewport"],
        record_video_dir=str(evidence_dir),   # Playwright records every test...
    )
    context.tracing.start(screenshots=True, snapshots=True, sources=True)

    # Refuse third-party hosts listed in config.yaml before anything loads.
    #
    # An ad network served an interstitial that consumed the first navigation
    # after a page load: the click reported success, the browser did not move,
    # and the next action spent its full timeout on a page nobody reached. It
    # fired on some runs and not others, so the same code passed and failed.
    #
    # Every framework defence against that is a recovery after the fact. Not
    # loading the ad removes the failure mode instead of handling it. The list
    # lives in config.yaml because WHICH hosts to refuse is a property of the
    # site under test; this code reads a list and knows nothing else.
    blocked_hosts = browser_config.get("block_hosts") or []
    blocked_count = {"n": 0}
    if blocked_hosts:
        def _refuse_blocked(route, request):
            if should_block_request(request.url, blocked_hosts):
                blocked_count["n"] += 1
                route.abort()
            else:
                route.continue_()

        context.route("**/*", _refuse_blocked)

    page = context.new_page()
    page.set_default_timeout(browser_config["timeout"])
    # Failed requests and HTTP errors, for failure messages to name (blocked
    # third parties excluded: those are refused on purpose).
    from pages.base_page import watch_network
    watch_network(page, ignore=lambda url: should_block_request(url, blocked_hosts))
    # pytest_runtest_call below reads it when the test fails.
    request.node._watched_page = page

    yield page

    if blocked_count["n"]:
        logger.info("Blocked %d third-party request(s) from %s.",
                    blocked_count["n"], ", ".join(map(str, blocked_hosts)))

    # Decide outcome from the hook-attached report (see makereport below).
    failed = getattr(request.node, "rep_call", None) is not None and request.node.rep_call.failed
    safe_name = request.node.name.replace("/", "_").replace("::", "_").replace(" ", "_")

    try:
        if failed:
            # Screenshot of final state
            try:
                page.screenshot(path=str(evidence_dir / f"{safe_name}.png"), full_page=True)
            except Exception:
                pass
            # Trace zip
            try:
                context.tracing.stop(path=str(evidence_dir / f"{safe_name}.trace.zip"))
            except Exception:
                pass
        else:
            # Passing test — discard the trace (don't write a zip)
            try:
                context.tracing.stop()
            except Exception:
                pass
    finally:
        video = page.video
        context.close()  # finalizes the video file on disk
        # Keep the video only on failure; rename to the test name, else delete.
        if video is not None:
            try:
                src = _Path(video.path())
                if failed:
                    src.replace(evidence_dir / f"{safe_name}.webm")
                else:
                    src.unlink(missing_ok=True)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────
# Failure-detection hook — makes each test's outcome available to
# fixtures (via request.node.rep_call) so the `page` fixture can
# capture evidence only when a test fails.
# ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
# Gherkin steps in the Allure report
#
# allure-pytest reports PYTEST, and this suite is written in Gherkin - so a
# scenario arrives as one row and which of its five steps failed is nowhere.
# For anyone who did not write the test, that is the only thing worth knowing.
#
# pytest-bdd already announces every step it runs; nothing was listening.
# ---------------------------------------------------------------------------
def pytest_bdd_before_step_call(request, feature, scenario, step, step_func,
                                step_func_args):
    from core.allure_steps import start_step
    start_step(request, step)


def pytest_bdd_after_step(request, feature, scenario, step, step_func,
                          step_func_args):
    from core.allure_steps import end_step
    end_step(request)


def pytest_bdd_step_error(request, feature, scenario, step, step_func,
                          step_func_args, exception):
    """Mark THIS step failed, leaving the ones before it green.

    That is the difference between "the cart test failed" and "it logged in,
    searched and added the product, then failed removing it".
    """
    from core.allure_steps import fail_step
    fail_step(request, exception)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Name the temporary server errors a failed test met, in its own message.

    Agent 4 re-runs a test whose failure names `HTTP 5xx` or `HTTP 429`
    (agent4_runner.yml, --only-rerun reads the exception message). A 503 on the
    action's OWN request - an add-to-cart call, a link followed to a page -
    surfaced as "cart row not found" or "element never appeared", named no
    HTTP error, and was reported as a test failure (PR #215, run of 26 Oct:
    two failures in a 503 burst). Requests the server later answered
    successfully - navigate() retries a page load - are not counted.
    """
    try:
        return (yield)
    except Exception as exc:                                   # noqa: BLE001
        page = getattr(item, "_watched_page", None)
        if page is not None:
            from pages.base_page import unrecovered_server_errors, with_server_errors
            restated = with_server_errors(exc, unrecovered_server_errors(page))
            if restated is not None:
                raise restated from exc
        raise


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)

    # Attach a plain-English CAUSE and FIX to every failure.
    #
    # A Playwright error says what the framework was doing, never what was
    # wrong with the application. "strict mode violation", "Timeout 30000ms",
    # `assert '' == 'qa_user'` - each needed someone with the whole repo in
    # their head and a trace file to interpret. Each also has a small number
    # of causes and a specific remedy, so those are printed next to the
    # failure instead of living in one person's memory.
    #
    # Written to the report SECTIONS, so it appears in the terminal output,
    # in reports/pytest-report.html and in the CI log - everywhere someone
    # might read a failure - without touching the assertion itself.
    #
    # The reading itself is core.failure_diagnosis.attach_diagnosis, NOT four
    # lines here. It has to read `report.caplog` as well as the traceback:
    # is_showing() swallows the Playwright error and logs it, so for the whole
    # readiness-probe class the traceback holds only `assert False` and the
    # sentence that classifies the failure sits in the CAPTURED LOG. This hook
    # passed the traceback alone, so those failures were reported
    # "unclassified" six lines under a log line naming the exact cause.
    #
    # Keeping the body importable is the other half of the fix: while it lived
    # inline, the only thing a guard could check was that diagnose() classifies
    # a string - never that the string this hook hands it is the one carrying
    # the answer. It was not.
    if report.failed:
        try:
            from core.failure_diagnosis import attach_diagnosis
            attach_diagnosis(report)

            # ...and put the reading, plus the screenshot, video and
            # trace, INTO the report.
            #
            # attach_diagnosis writes to report.sections, which pytest
            # prints and junit.xml carries and allure-pytest never
            # reads. The evidence files sit on disk under names nobody
            # following a report will guess. Everything attached here
            # already existed; none of it was reachable from the report
            # somebody is actually handed.
            from core.allure_steps import attach_failure_evidence
            attach_failure_evidence(report, Path("reports/failure-evidence"))
        except Exception:                                 # noqa: BLE001
            pass

    # The FILES are attached at TEARDOWN, not here.
    #
    # The page fixture writes the screenshot, video and trace in its teardown,
    # which pytest runs AFTER this hook has already produced the call-phase
    # report. Attaching them above therefore globbed a directory that did not
    # yet contain them: the "Why this failed" text arrived in Allure and the
    # evidence never did, so a failed test showed an explanation with nothing
    # to look at - the one place a screenshot is worth having.
    #
    # By the teardown report the files exist. Allure attaches to whichever
    # test is current, so they land on the right test either way.
    if report.when == "teardown" and getattr(item, "rep_call", None) is not None \
            and item.rep_call.failed:
        try:
            from core.allure_steps import attach_failure_evidence
            attach_failure_evidence(item.rep_call,
                                    Path("reports/failure-evidence"),
                                    files_only=True)
        except Exception:                                 # noqa: BLE001
            # Diagnosis is a convenience. It must never be able to turn a
            # test failure into a collection error or mask the real result.
            pass