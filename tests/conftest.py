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
def page(browser, config) -> Page:
    """Fresh browser tab (context) for each test — full isolation."""
    browser_config = config["browser"]
    context = browser.new_context(
        viewport=browser_config["viewport"],
    )
    page = context.new_page()
    page.set_default_timeout(browser_config["timeout"])
    yield page
    context.close()