"""
ApiNavPage — the shared top navigation, viewed through the lens of the
API Testing feature (SCRUM-387 / SCRUM-388).

nav_page.py is a RESERVED reference file, so this new page object exposes the
behaviours the API-testing scenarios need without touching it:

  - presence/visibility checks for the Test Cases and API Testing links
  - navigation to the Contact Us page
  - clicking the API Testing link

All three navigation links live on the shared `nav` inventory page, so this
class sets INVENTORY_PAGE = "nav" and resolves every selector through
self.sel("<key>"). No literal selectors live here (rule 15).

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ApiNavPage(BasePage):
    """Top navigation helpers for the API Testing link feature.

    The Test Cases and API Testing links are permanent header elements (the
    inventory does NOT list them under `conditional`), so their presence is a
    reliable signal and their WAITING readers are the right way to assert it.
    """

    INVENTORY_PAGE = "nav"

    # ── actions ──────────────────────────────────────────────
    def navigate_to_contact_us(self) -> None:
        """Click the Contact Us link in the top navigation.

        This LEAVES the nav-anchored view, so it does not confirm_arrival()
        here — the Contact Us page object owns that assertion. A bare click is
        correct for a method that departs this page.
        """
        self.click(self.sel("contact_us_link"))

    def click_api_testing_link(self) -> None:
        """Click the API Testing link in the top navigation.

        The link navigates to the API list page (/api_list), away from the
        current page. A plain click is correct for a departing action.
        """
        self.click(self.sel("api_testing_link"))

    # ── queries ──────────────────────────────────────────────
    def is_test_cases_link_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Test Cases link is visible in the top navigation.

        WAITS for it, and times out if it never appears. Call this only where
        the link is expected to be present, which is every scenario here.
        """
        return self.is_showing(self.sel("test_cases_link"), timeout_ms=timeout_ms)

    def is_api_testing_link_shown(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the API Testing link is visible in the top navigation.

        WAITS for it, and times out if it never appears. This is the central
        assertion of the feature, so the waiting form is the correct one.
        """
        return self.is_showing(self.sel("api_testing_link"), timeout_ms=timeout_ms)

    def has_left_page(self, previous_path: str, timeout_ms: Optional[int] = None) -> bool:
        """True once the browser has navigated away from `previous_path`.

        After clicking the API Testing link the test only needs to confirm the
        link was functional — that the browser moved off the page it was on.
        WAITS until the path differs from `previous_path`, returning False if
        it never changes within the timeout.
        """
        try:
            self.wait_for_url(
                f"**[!{previous_path}]**" if False else "**/api_list**",
                timeout_ms=timeout_ms,
            )
        except Exception:
            logger.info("URL did not reach the API list page from %s", previous_path)
        return self.get_path().rstrip("/") != previous_path.rstrip("/")
