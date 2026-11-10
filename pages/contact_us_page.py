"""
ContactUsPage — the Contact Us form screen.

New page object. Selectors come from the `contact_us` page in the app
inventory; this file holds none of its own.

Conventions followed (see pages/login_page.py for the worked example):
  - INVENTORY_PAGE set, selectors resolved via self.sel("<key>")
  - business-verb method names that say WHAT they act on
  - every method uses a BasePage helper; no raw self.page.* calls
  - presence asserted with a WAITING reader; absence proved on a page that
    is first shown to BE loaded, because the success element is PERMANENT
    (not conditional in the sense of leaving the DOM — it is in the DOM from
    the start, merely hidden), so an absence check alone would also pass on a
    blank screen
  - the submit opens a native confirmation dialog, so accept_next_dialog() is
    armed BEFORE the submit click, per the inventory note

App: https://automationexercise.com
"""
from typing import Optional

import logging

from pages.base_page import BasePage


logger = logging.getLogger(__name__)


class ContactUsPage(BasePage):
    """Contact Us form. Selectors: see `contact_us` in the app inventory."""

    INVENTORY_PAGE = "contact_us"

    # ── actions ──────────────────────────────────────────────
    def open_contact_us(self, base_url: str) -> None:
        """Navigate directly to the Contact Us page."""
        self.navigate(f"{base_url.rstrip('/')}{self.page_url()}")

    def fill_contact_form(self, name: str, email: str, subject: str, message: str) -> None:
        """Fill the four contact fields without submitting.

        Confirms it is on this page before filling: a fill issued from
        elsewhere does not fail fast — Playwright waits the full timeout and
        then blames the field selector, which is not the fault.

        `email` may be empty: that is valid test data for the negative
        scenario, where the browser's own required-field validation is
        expected to block the submit.
        """
        self.require_own_page()
        self.fill(self.sel("contact_name_input"), name)
        self.fill(self.sel("contact_email_input"), email)
        self.fill(self.sel("contact_subject_input"), subject)
        self.fill(self.sel("contact_message_input"), message)

    def submit_contact_form(self) -> None:
        """Submit the form, accepting the native confirmation dialog.

        Submitting opens a browser confirm dialog ('Press OK to proceed!').
        accept_next_dialog() is armed BEFORE the click, or the submit waits
        forever for a dialog nobody answered.

        When the email field is empty the browser blocks the submit with its
        own required-field validation, so no dialog opens — accepting a dialog
        that never appears is harmless.
        """
        self.accept_next_dialog()
        self.click(self.sel("contact_submit_button"))

    def click_home_button(self) -> None:
        """Click the Home button shown after a successful submit."""
        self.click(self.sel("contact_home_button"))

    # ── queries ──────────────────────────────────────────────
    def is_loaded(self, timeout_ms: Optional[int] = None) -> bool:
        """True once the Contact Us form heading is on screen. WAITS for it."""
        return self.is_showing(self.sel("contact_heading"), timeout_ms=timeout_ms)

    def has_success_message(self) -> bool:
        """True once the submission success message is visible. WAITS for it.

        Call this only where success IS expected. The message is present in the
        DOM but hidden until a successful submit, so a non-waiting read would
        race the submit. To assert NO success is shown, use
        is_success_message_absent(), which does not wait.
        """
        return self.is_showing(self.sel("contact_success_message"))

    def is_success_message_absent(self) -> bool:
        """True when the success message is NOT shown, on a page proven loaded.

        The success element is a PERMANENT part of this page — it is in the DOM
        from the start, merely hidden until a successful submit — so the
        inventory does not treat it as a come-and-go conditional. That means it
        is just as absent before the page has rendered, or on any other page,
        and an absence check alone would pass on a blank screen. Prove the page
        first, THEN that the success message is not showing.

        is_gone() returns at once when the element is hidden and waits only
        while it is still showing, so the expected (absent) case costs nothing.
        """
        return self.is_loaded() and self.is_gone(self.sel("contact_success_message"))

    def get_feedback_email_link_text(self) -> str:
        """Return the VISIBLE text of the feedback email link. WAITS for it.

        SCRUM-366 asserts this reads as the email address itself — not the
        Test Cases page's 'Write to our QA team' wording. The link is a
        permanent part of the contact page's feedback section, so a waiting
        read is safe: the element is always rendered once the page is loaded.
        """
        self.wait_visible(self.sel("feedback_automationexercise_com_link"))
        return self.get_text(self.sel("feedback_automationexercise_com_link"))

    def get_feedback_email_link_href(self) -> str:
        """Return the href attribute of the feedback email link. WAITS for it.

        SCRUM-366 asserts clicking opens an email client, so the href must be a
        'mailto:' link. Returns the raw href string for the step definition to
        inspect.
        """
        self.wait_visible(self.sel("feedback_automationexercise_com_link"))
        return self.get_attribute(self.sel("feedback_automationexercise_com_link"), "href") or ""
