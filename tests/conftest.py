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

# def load_config():
#     """Load YAML config once."""
#     config_path = Path(__file__).parent.parent / "config" / "config.yaml"
#     with open(config_path) as f:
#         return yaml.safe_load(f)


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
    browser = playwright_instance.chromium.launch(
        headless=browser_config["headless"],
        slow_mo=browser_config["slow_mo"],
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