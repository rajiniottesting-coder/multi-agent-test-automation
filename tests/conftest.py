"""
Pytest fixtures shared across all tests.
The `page` fixture provides a fresh Playwright Browser tab for each scenario.
"""
import os
import yaml
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Browser
from dotenv import load_dotenv
from config.paths import CONFIG_YAML

load_dotenv()


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
    page = context.new_page()
    page.set_default_timeout(browser_config["timeout"])

    yield page

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
        except Exception:                                 # noqa: BLE001
            # Diagnosis is a convenience. It must never be able to turn a
            # test failure into a collection error or mask the real result.
            pass