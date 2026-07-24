"""Fixtures shared by all step-definition modules.

Only fixtures belong here. Step definitions are declared in each step-def
module, not in this file.

`page` and `base_url` are inherited from tests/conftest.py.
"""
import os

import pytest

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage


# === Page objects ===

@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    return InventoryPage(page)


# === Credentials ===

@pytest.fixture(scope="session")
def credentials():
    """Resolve a role name to (username, password) from the environment.

    For role "standard":
        username -> APP_USER_STANDARD
        password -> APP_PASSWORD_STANDARD, else APP_PASSWORD
    """
    def _for(role: str) -> tuple[str, str]:
        key = role.strip().upper().replace("-", "_").replace(" ", "_")
        user = os.getenv(f"APP_USER_{key}")
        if not user:
            raise RuntimeError(
                f"Missing credential for role '{role}'. Set APP_USER_{key}."
            )
        password = os.getenv(f"APP_PASSWORD_{key}") or os.getenv("APP_PASSWORD")
        if not password:
            raise RuntimeError(
                f"Missing password for role '{role}'. "
                f"Set APP_PASSWORD_{key} or APP_PASSWORD."
            )
        return user, password

    return _for