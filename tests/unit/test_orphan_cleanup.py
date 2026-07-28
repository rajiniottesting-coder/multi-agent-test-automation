"""
Unit tests for validators.orphan_cleanup.

DESIGN PRINCIPLE: every test uses synthetic app-neutral content to
prove the cleanup logic is generic. We use banking, CMS, and finance
shapes to verify the same code works across domains.
"""
from __future__ import annotations

import textwrap

import pytest

from validators.orphan_cleanup import (
    OrphanPageMethod,
    OrphanStepDef,
    cleanup_orphans_after_removal,
    comment_out_orphan_page_methods,
    extract_steps_in_removed_scenarios,
    find_orphan_page_methods,
    find_orphan_step_defs,
)


# ════════════════════════════════════════════════════════════════════
# Fixtures: synthetic banking app (no references to the demo app under test)
# ════════════════════════════════════════════════════════════════════

BANKING_FEATURE_BEFORE = textwrap.dedent("""\
    Feature: Account transactions

      # JIRA: BANK-101 (hash: aaaaaaaa)
      Scenario: Customer views balance
        Given I am logged in as a retail customer
        When I open the dashboard
        Then I should see my account balance

      # JIRA: BANK-102 (hash: bbbbbbbb)
      Scenario: Customer transfers funds
        Given I am logged in as a retail customer
        When I transfer 500 to account "12345"
        Then I should see a confirmation toast

      # JIRA: BANK-103 (hash: cccccccc)
      Scenario: Customer requests a paper statement
        Given I am logged in as a retail customer
        When I request a paper statement
        Then a paper statement should be queued for mailing
    """)


BANKING_FEATURE_AFTER = textwrap.dedent("""\
    Feature: Account transactions

      # JIRA: BANK-101 (hash: aaaaaaaa)
      Scenario: Customer views balance
        Given I am logged in as a retail customer
        When I open the dashboard
        Then I should see my account balance

      # JIRA: BANK-102 (hash: bbbbbbbb)
      Scenario: Customer transfers funds
        Given I am logged in as a retail customer
        When I transfer 500 to account "12345"
        Then I should see a confirmation toast
    """)


BANKING_STEP_DEFS = textwrap.dedent('''\
    """Step defs for account transactions feature."""
    import pytest
    from pytest_bdd import given, when, then, parsers
    from pages.account_page import AccountPage
    from pages.statement_page import StatementPage


    @pytest.fixture
    def account_page(page):
        return AccountPage(page)


    @pytest.fixture
    def statement_page(page):
        return StatementPage(page)


    @given("I am logged in as a retail customer")
    def login_as_retail(account_page):
        account_page.login_with_role("retail")


    @when("I open the dashboard")
    def open_dashboard(account_page):
        account_page.open_dashboard()


    @then("I should see my account balance")
    def verify_balance_visible(account_page):
        assert account_page.is_balance_visible()


    @when(parsers.parse('I transfer {amount:d} to account "{account_number}"'))
    def transfer_funds(account_page, amount, account_number):
        account_page.initiate_transfer(amount, account_number)


    @then("I should see a confirmation toast")
    def verify_confirmation(account_page):
        assert account_page.has_confirmation_toast()


    @when("I request a paper statement")
    def request_paper_statement(statement_page):
        statement_page.click_request_paper_statement()


    @then("a paper statement should be queued for mailing")
    def verify_statement_queued(statement_page):
        assert statement_page.is_statement_queued_for_mailing()
    ''')


BANKING_PAGE_STATEMENT = textwrap.dedent('''\
    """Statement page object."""
    from pages.base_page import BasePage


    class StatementPage(BasePage):
        REQUEST_PAPER_BUTTON = "[data-testid='request-paper']"
        QUEUED_INDICATOR = "[data-testid='queued-status']"

        def click_request_paper_statement(self) -> None:
            """Click the 'request paper statement' button."""
            self.page.locator(self.REQUEST_PAPER_BUTTON).click()

        def is_statement_queued_for_mailing(self) -> bool:
            """Check if the queued indicator is visible."""
            return self.page.locator(self.QUEUED_INDICATOR).is_visible()

        def download_pdf_statement(self) -> bytes:
            """Used by another scenario in a different feature — should not be orphan."""
            return self.page.locator("[data-testid='pdf-link']").screenshot()
    ''')


BANKING_PAGE_ACCOUNT = textwrap.dedent('''\
    """Account page object."""
    from pages.base_page import BasePage


    class AccountPage(BasePage):
        BALANCE = "[data-testid='balance']"
        TOAST = "[data-testid='toast']"

        def login_with_role(self, role: str) -> None:
            self.page.fill("[name='role']", role)
            self.page.click("button[type='submit']")

        def open_dashboard(self) -> None:
            self.page.click("[data-testid='dashboard-link']")

        def is_balance_visible(self) -> bool:
            return self.page.locator(self.BALANCE).is_visible()

        def initiate_transfer(self, amount: int, account: str) -> None:
            self.page.fill("[name='amount']", str(amount))
            self.page.fill("[name='account']", account)
            self.page.click("button[type='submit']")

        def has_confirmation_toast(self) -> bool:
            return self.page.locator(self.TOAST).is_visible()
    ''')


# ════════════════════════════════════════════════════════════════════
# Tests for extract_steps_in_removed_scenarios
# ════════════════════════════════════════════════════════════════════

class TestExtractStepsInRemovedScenarios:

    def test_extracts_steps_for_single_removed_key(self):
        steps = extract_steps_in_removed_scenarios(
            BANKING_FEATURE_BEFORE, ["BANK-103"]
        )
        # BANK-103 has 3 steps: Given, When, Then
        phrases = [phrase for _kw, phrase in steps]
        assert "I am logged in as a retail customer" in phrases
        assert "I request a paper statement" in phrases
        assert "a paper statement should be queued for mailing" in phrases
        assert len(steps) == 3

    def test_returns_empty_when_no_keys_provided(self):
        steps = extract_steps_in_removed_scenarios(BANKING_FEATURE_BEFORE, [])
        assert steps == []

    def test_returns_empty_when_key_not_present_in_file(self):
        steps = extract_steps_in_removed_scenarios(
            BANKING_FEATURE_BEFORE, ["NONEXISTENT-999"]
        )
        assert steps == []

    def test_extracts_steps_for_multiple_removed_keys(self):
        steps = extract_steps_in_removed_scenarios(
            BANKING_FEATURE_BEFORE, ["BANK-102", "BANK-103"]
        )
        phrases = [phrase for _kw, phrase in steps]
        assert 'I transfer 500 to account "12345"' in phrases
        assert "I request a paper statement" in phrases


# ════════════════════════════════════════════════════════════════════
# Tests for find_orphan_step_defs
# ════════════════════════════════════════════════════════════════════

class TestFindOrphanStepDefs:

    def test_detects_orphan_step_def_in_banking_scenario(self):
        """BANK-103 was removed. Its unique step defs are now orphan."""
        removed_steps = extract_steps_in_removed_scenarios(
            BANKING_FEATURE_BEFORE, ["BANK-103"]
        )
        # Surviving steps come from BANK-101 and BANK-102
        from validators.gherkin_analyzer import _extract_feature_steps
        surviving = _extract_feature_steps(BANKING_FEATURE_AFTER)

        orphans = find_orphan_step_defs(
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            steps_in_removed_scenarios=removed_steps,
            steps_in_surviving_feature=surviving,
        )

        orphan_names = {o.function_name for o in orphans}
        # request_paper_statement and verify_statement_queued are unique to BANK-103
        assert "request_paper_statement" in orphan_names
        assert "verify_statement_queued" in orphan_names

    def test_does_not_flag_shared_steps_as_orphan(self):
        """'Given I am logged in as retail' appears in BANK-101 AND BANK-103.
        Even though BANK-103 is removed, BANK-101 still uses login_as_retail.
        It must NOT be flagged as orphan."""
        removed_steps = extract_steps_in_removed_scenarios(
            BANKING_FEATURE_BEFORE, ["BANK-103"]
        )
        from validators.gherkin_analyzer import _extract_feature_steps
        surviving = _extract_feature_steps(BANKING_FEATURE_AFTER)

        orphans = find_orphan_step_defs(
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            steps_in_removed_scenarios=removed_steps,
            steps_in_surviving_feature=surviving,
        )

        orphan_names = {o.function_name for o in orphans}
        assert "login_as_retail" not in orphan_names

    def test_returns_empty_when_nothing_removed(self):
        orphans = find_orphan_step_defs(
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            steps_in_removed_scenarios=[],
            steps_in_surviving_feature=[],
        )
        assert orphans == []

    def test_returns_empty_when_all_steps_still_alive(self):
        """If BANK-102 is removed but BANK-103 survives with same transfer step,
        the transfer step def is NOT orphan."""
        # Construct a feature where BANK-102 and BANK-103 share a step
        feature = BANKING_FEATURE_BEFORE  # keep BANK-103 alive
        from validators.gherkin_analyzer import _extract_feature_steps

        removed_steps = extract_steps_in_removed_scenarios(feature, ["BANK-102"])
        surviving = _extract_feature_steps(feature)  # all 3 scenarios still in surviving content

        orphans = find_orphan_step_defs(
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            steps_in_removed_scenarios=removed_steps,
            steps_in_surviving_feature=surviving,
        )
        # All step defs match SOME surviving step → no orphans.
        assert orphans == []

    def test_works_for_parsers_parse_decorators(self):
        """Make sure parsers.parse-style decorators are correctly matched."""
        # If BANK-102 (which uses parsers.parse) is removed and nothing else
        # uses transfer, transfer_funds should be orphan.
        feature_minus_102 = textwrap.dedent("""\
            Feature: Account transactions

              # JIRA: BANK-101 hash:aaaaaaaa
              Scenario: Customer views balance
                Given I am logged in as a retail customer
                When I open the dashboard
                Then I should see my account balance
            """)
        removed_steps = extract_steps_in_removed_scenarios(
            BANKING_FEATURE_BEFORE, ["BANK-102", "BANK-103"]
        )
        from validators.gherkin_analyzer import _extract_feature_steps
        surviving = _extract_feature_steps(feature_minus_102)

        orphans = find_orphan_step_defs(
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            steps_in_removed_scenarios=removed_steps,
            steps_in_surviving_feature=surviving,
        )
        orphan_names = {o.function_name for o in orphans}
        assert "transfer_funds" in orphan_names


# ════════════════════════════════════════════════════════════════════
# Tests for find_orphan_page_methods
# ════════════════════════════════════════════════════════════════════

class TestFindOrphanPageMethods:

    def test_detects_page_method_called_only_by_orphan_step_def(self):
        """If request_paper_statement is orphan and it's the only caller of
        StatementPage.click_request_paper_statement, that method is orphan."""
        # Simulate: BANK-103 removed → request_paper_statement and
        # verify_statement_queued are orphan step defs.
        orphan_defs = [
            OrphanStepDef(
                file_path="tests/step_defs/test_account.py",
                function_name="request_paper_statement",
                decorator_phrase="I request a paper statement",
                decorator_kind="when",
                line_start=33,  # actual line of @when decorator in BANKING_STEP_DEFS
                line_end=35,
            ),
            OrphanStepDef(
                file_path="tests/step_defs/test_account.py",
                function_name="verify_statement_queued",
                decorator_phrase="a paper statement should be queued for mailing",
                decorator_kind="then",
                line_start=38,
                line_end=40,
            ),
        ]

        # Build a step_def file where ONLY the orphan funcs call these methods
        orphans = find_orphan_page_methods(
            orphan_step_defs=orphan_defs,
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            page_object_files={
                "pages/statement_page.py": BANKING_PAGE_STATEMENT,
                "pages/account_page.py": BANKING_PAGE_ACCOUNT,
            },
        )

        method_names = {(o.class_name, o.method_name) for o in orphans}
        assert ("StatementPage", "click_request_paper_statement") in method_names
        assert ("StatementPage", "is_statement_queued_for_mailing") in method_names

    def test_does_not_flag_page_method_used_by_surviving_step_def(self):
        """AccountPage.open_dashboard is called by surviving step def → not orphan."""
        # Pretend ONLY request_paper_statement is orphan
        orphan_defs = [
            OrphanStepDef(
                file_path="tests/step_defs/test_account.py",
                function_name="request_paper_statement",
                decorator_phrase="I request a paper statement",
                decorator_kind="when",
                line_start=33,
                line_end=35,
            ),
        ]

        orphans = find_orphan_page_methods(
            orphan_step_defs=orphan_defs,
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            page_object_files={
                "pages/account_page.py": BANKING_PAGE_ACCOUNT,
            },
        )

        method_names = {o.method_name for o in orphans}
        assert "open_dashboard" not in method_names
        assert "is_balance_visible" not in method_names

    def test_returns_empty_when_no_orphan_step_defs(self):
        orphans = find_orphan_page_methods(
            orphan_step_defs=[],
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            page_object_files={"pages/statement_page.py": BANKING_PAGE_STATEMENT},
        )
        assert orphans == []

    def test_skips_private_methods(self):
        """Methods starting with _ should never be flagged as orphan."""
        page_with_private = textwrap.dedent('''\
            from pages.base_page import BasePage

            class TestPage(BasePage):
                def _internal_helper(self):
                    pass

                def some_action(self):
                    pass
            ''')
        # Pretend some_action is called by an orphan step def
        step_def = textwrap.dedent('''\
            from pytest_bdd import when

            @when("I do thing")
            def do_thing(page_obj):
                page_obj.some_action()
                page_obj._internal_helper()
            ''')
        orphan_defs = [
            OrphanStepDef(
                file_path="tests/step_defs/test_x.py",
                function_name="do_thing",
                decorator_phrase="I do thing",
                decorator_kind="when",
                line_start=3,
                line_end=6,
            )
        ]
        orphans = find_orphan_page_methods(
            orphan_step_defs=orphan_defs,
            step_def_files={"tests/step_defs/test_x.py": step_def},
            page_object_files={"pages/test_page.py": page_with_private},
        )
        names = {o.method_name for o in orphans}
        assert "_internal_helper" not in names
        assert "some_action" in names  # public method legitimately flagged


# ════════════════════════════════════════════════════════════════════
# Tests for comment_out_orphan_page_methods
# ════════════════════════════════════════════════════════════════════

class TestCommentOutOrphanPageMethods:

    def test_comments_out_method_and_inserts_banner(self):
        page_content = textwrap.dedent('''\
            from pages.base_page import BasePage

            class MyPage(BasePage):
                def alive_method(self):
                    pass

                def dead_method(self):
                    self.page.click("#x")
            ''')
        # dead_method starts at line 7
        orphan = OrphanPageMethod(
            file_path="pages/my_page.py",
            class_name="MyPage",
            method_name="dead_method",
            line_start=7,
            line_end=8,
        )
        result = comment_out_orphan_page_methods(
            page_content, [orphan], ["BANK-103"]
        )
        assert "AI-ORPHAN" in result
        assert "BANK-103" in result
        # dead_method's def line should be commented
        assert "# def dead_method" in result
        # alive_method must NOT be commented
        assert "    def alive_method(self):" in result
        # The class declaration is untouched
        assert "class MyPage(BasePage):" in result

    def test_preserves_unrelated_content(self):
        page_content = textwrap.dedent('''\
            from pages.base_page import BasePage

            class CmsPage(BasePage):
                """A CMS page object."""

                ARTICLE_BODY = "[data-testid='body']"

                def publish_article(self):
                    self.page.click("#publish")

                def archive_article(self):
                    self.page.click("#archive")
            ''')
        # archive_article starts around line 11
        orphan = OrphanPageMethod(
            file_path="pages/cms_page.py",
            class_name="CmsPage",
            method_name="archive_article",
            line_start=11,
            line_end=12,
        )
        result = comment_out_orphan_page_methods(
            page_content, [orphan], ["CMS-50"]
        )
        # Class-level constant must remain
        assert 'ARTICLE_BODY = "[data-testid=\'body\']"' in result
        # publish_article must remain
        assert "def publish_article(self):" in result
        # archive_article commented
        assert "# def archive_article" in result

    def test_returns_unchanged_when_no_orphans(self):
        page_content = "class X:\n    def foo(self): pass\n"
        result = comment_out_orphan_page_methods(page_content, [], ["KEY-1"])
        assert result == page_content


# ════════════════════════════════════════════════════════════════════
# End-to-end test on banking scenario
# ════════════════════════════════════════════════════════════════════

class TestCleanupOrphansAfterRemoval:

    def test_full_banking_workflow_bank103_removed(self):
        """Full happy path: BANK-103 deleted in Jira. Verify orphan detection
        and page-object commenting work end to end."""
        step_def_files = {
            "tests/step_defs/test_account.py": BANKING_STEP_DEFS,
        }
        page_object_files = {
            "pages/statement_page.py": BANKING_PAGE_STATEMENT,
            "pages/account_page.py": BANKING_PAGE_ACCOUNT,
        }

        (
            _new_step_defs,
            new_pages,
            orphan_defs,
            orphan_methods,
        ) = cleanup_orphans_after_removal(
            old_feature_content=BANKING_FEATURE_BEFORE,
            new_feature_content=BANKING_FEATURE_AFTER,
            removed_jira_keys=["BANK-103"],
            step_def_files=step_def_files,
            page_object_files=page_object_files,
        )

        # Confirm orphan step defs found
        orphan_step_names = {o.function_name for o in orphan_defs}
        assert "request_paper_statement" in orphan_step_names
        assert "verify_statement_queued" in orphan_step_names

        # Confirm orphan page methods found
        orphan_method_names = {(o.class_name, o.method_name) for o in orphan_methods}
        assert ("StatementPage", "click_request_paper_statement") in orphan_method_names
        assert ("StatementPage", "is_statement_queued_for_mailing") in orphan_method_names

        # Page object file should have these methods commented out
        updated_statement_page = new_pages["pages/statement_page.py"]
        assert "AI-ORPHAN" in updated_statement_page
        assert "BANK-103" in updated_statement_page
        assert "# def click_request_paper_statement" in updated_statement_page
        assert "# def is_statement_queued_for_mailing" in updated_statement_page
        # download_pdf_statement (used elsewhere theoretically) must remain alive
        # since no step def references it in our test data either, but we
        # only flag methods CALLED by orphan step defs. Methods never called
        # from any step def are simply ignored — never flagged.
        assert "def download_pdf_statement" in updated_statement_page
        assert "# def download_pdf_statement" not in updated_statement_page

        # Account page should be untouched (none of its methods are orphan)
        assert new_pages["pages/account_page.py"] == BANKING_PAGE_ACCOUNT

    def test_reserved_files_are_skipped(self):
        """If a page object is in reserved_file_paths, it must NOT be modified."""
        page_object_files = {
            "pages/statement_page.py": BANKING_PAGE_STATEMENT,
        }
        (_sd, new_pages, _od, orphan_methods) = cleanup_orphans_after_removal(
            old_feature_content=BANKING_FEATURE_BEFORE,
            new_feature_content=BANKING_FEATURE_AFTER,
            removed_jira_keys=["BANK-103"],
            step_def_files={"tests/step_defs/test_account.py": BANKING_STEP_DEFS},
            page_object_files=page_object_files,
            reserved_file_paths={"pages/statement_page.py"},
        )
        # No orphans found because the file was excluded
        assert orphan_methods == []
        # File content unchanged
        assert new_pages["pages/statement_page.py"] == BANKING_PAGE_STATEMENT

    def test_no_removed_keys_is_noop(self):
        page_object_files = {"pages/statement_page.py": BANKING_PAGE_STATEMENT}
        step_def_files = {"tests/step_defs/test_account.py": BANKING_STEP_DEFS}
        (sd, pages, od, om) = cleanup_orphans_after_removal(
            old_feature_content=BANKING_FEATURE_BEFORE,
            new_feature_content=BANKING_FEATURE_BEFORE,
            removed_jira_keys=[],
            step_def_files=step_def_files,
            page_object_files=page_object_files,
        )
        assert sd == step_def_files
        assert pages == page_object_files
        assert od == []
        assert om == []


# ════════════════════════════════════════════════════════════════════
# Project-agnostic verification: same code works with a CMS shape
# ════════════════════════════════════════════════════════════════════

class TestGenericAcrossDomains:

    def test_works_for_cms_publishing_app(self):
        """Same code, completely different domain (CMS), confirms zero
        hardcoded assumptions about banking, the demo app, or any other app."""
        cms_feature_before = textwrap.dedent("""\
            Feature: Article management

              # JIRA: CMS-1 (hash: aaaaaaaa)
              Scenario: Editor creates an article
                Given I am logged in as an editor
                When I create an article titled "Hello"
                Then the article should appear in the drafts list

              # JIRA: CMS-2 (hash: bbbbbbbb)
              Scenario: Editor schedules an article for tweet
                Given I am logged in as an editor
                When I schedule the article for tweet
                Then a tweet should be queued in the social scheduler
            """)
        cms_feature_after = textwrap.dedent("""\
            Feature: Article management

              # JIRA: CMS-1 (hash: aaaaaaaa)
              Scenario: Editor creates an article
                Given I am logged in as an editor
                When I create an article titled "Hello"
                Then the article should appear in the drafts list
            """)
        cms_step_defs = textwrap.dedent('''\
            import pytest
            from pytest_bdd import given, when, then, parsers
            from pages.editor_page import EditorPage
            from pages.social_page import SocialPage

            @pytest.fixture
            def editor_page(page):
                return EditorPage(page)

            @pytest.fixture
            def social_page(page):
                return SocialPage(page)

            @given("I am logged in as an editor")
            def login_editor(editor_page):
                editor_page.login("editor")

            @when(parsers.parse('I create an article titled "{title}"'))
            def create_article(editor_page, title):
                editor_page.create_article_with_title(title)

            @then("the article should appear in the drafts list")
            def verify_in_drafts(editor_page):
                assert editor_page.article_in_drafts()

            @when("I schedule the article for tweet")
            def schedule_tweet(social_page):
                social_page.schedule_tweet_now()

            @then("a tweet should be queued in the social scheduler")
            def verify_tweet_queued(social_page):
                assert social_page.tweet_in_queue()
            ''')
        cms_page_social = textwrap.dedent('''\
            from pages.base_page import BasePage

            class SocialPage(BasePage):
                def schedule_tweet_now(self):
                    self.page.click("#schedule-tweet")

                def tweet_in_queue(self):
                    return self.page.locator("#tweet-queue-row").is_visible()
            ''')

        (_sd, new_pages, orphan_defs, orphan_methods) = cleanup_orphans_after_removal(
            old_feature_content=cms_feature_before,
            new_feature_content=cms_feature_after,
            removed_jira_keys=["CMS-2"],
            step_def_files={"tests/step_defs/test_articles.py": cms_step_defs},
            page_object_files={"pages/social_page.py": cms_page_social},
        )

        orphan_step_names = {o.function_name for o in orphan_defs}
        assert "schedule_tweet" in orphan_step_names
        assert "verify_tweet_queued" in orphan_step_names

        orphan_method_names = {o.method_name for o in orphan_methods}
        assert "schedule_tweet_now" in orphan_method_names
        assert "tweet_in_queue" in orphan_method_names

        # Confirm comment-out applied
        assert "# def schedule_tweet_now" in new_pages["pages/social_page.py"]
        assert "AI-ORPHAN" in new_pages["pages/social_page.py"]
        assert "CMS-2" in new_pages["pages/social_page.py"]