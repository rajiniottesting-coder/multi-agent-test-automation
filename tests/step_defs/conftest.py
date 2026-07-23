"""Shared page-object fixtures.

SCOPE OF THIS FILE — deliberately narrow
-----------------------------------------
This file holds ONLY fixtures (page-object constructors). It contains NO step
definitions, by design.

Fixtures MUST live here because pytest resolves fixtures hierarchically: a
fixture defined in one test module is invisible to every other module, but a
fixture in conftest.py is available to every module in this directory and
below. `page` and `base_url` come from the parent tests/conftest.py and are
inherited automatically — never redefine them here.

Step definitions do NOT belong here. Each step-def module declares every step
its own feature uses (see tests/step_defs/test_login.py). pytest-bdd step
definitions are module-scoped fixtures, so two modules declaring the same step
text each resolve their own copy and never collide — which means there is no
"is this step shared?" decision to make, and no cross-file dependency to
maintain as the suite grows.

ADDING A NEW PAGE OBJECT
------------------------
Add a fixture here, following the pattern below. That is the only change this
file needs, for any application of any size.
"""
import pytest

from pages.login_page import LoginPage
from pages.inventory_page import InventoryPage


@pytest.fixture
def login_page(page):
    return LoginPage(page)


@pytest.fixture
def inventory_page(page):
    return InventoryPage(page)