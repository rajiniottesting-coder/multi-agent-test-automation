"""An absolute assertion on state the application keeps between runs.

WHAT HAPPENED
    From the trace, unambiguously: one add-to-cart click in the whole run, one
    item added, and the collection read half a second after arriving held two.
    The second was left behind by a previous run against the same shared
    account.

        AssertionError: Expected exactly 1 product(s), got ['A', 'B']
        assert 2 == 1

    No wait fixes that. The retrying count helper added for an earlier failure
    would have retried for thirty seconds and found the same leftover, because
    the leftover is really there. The scenario asserted an ABSOLUTE number
    against state it did not create and does not own.

WHY THIS IS A GATE AND NOT GUIDANCE
    It was guidance, in the context modules, for months. It was regenerated
    away every time. A model reading "assert relatively" alongside a test case
    that says "should contain exactly one" writes what the test case says, and
    that is not unreasonable of it - the test case is the requirement.

    So the requirement has to be met a different way: the scenario registers
    its own account, or it clears the state in a Given. Both are things the
    generator can do. Neither is something it will do because a paragraph
    asked nicely.

THE RULE IS DECLARED, NOT ASSUMED
    It fires only where the INVENTORY says a page holds state that survives
    the run. An application without shared per-user state is untouched; one
    that has it says so in the inventory, which is where app knowledge lives.
"""
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

import re

from validators.method_resolution_validator import (
    _feature_in_batch,
    validate_persistent_state_assertions,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project whose inventory declares one persistent page and one not."""
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "Test App",
        "pages": {
            "basket": {
                "url": "/basket",
                "page_object_class": "BasketPage",
                "elements": {"rows": "#rows"},
                "persistent_state": True,
            },
            "listing": {
                "url": "/listing",
                "page_object_class": "ListingPage",
                "elements": {"cards": ".card"},
            },
        },
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n"
        "  name: Test App\n"
        "  inventory_file: app_inventory/app.json\n", encoding="utf-8")
    return tmp_path


def _steps(body: str) -> SimpleNamespace:
    return SimpleNamespace(
        file_path="tests/step_defs/test_flow.py",
        content=textwrap.dedent(body),
    )


# ─────────────────────────────────────────────────────────────────────────
# The shapes that must be rejected
# ─────────────────────────────────────────────────────────────────────────

def test_a_count_read_into_a_local_is_still_absolute(project):
    """The exact code that shipped. It never names the fixture inside the
    assertion - it reads into a local first - which is how the first draft of
    this validator passed it."""
    errors = validate_persistent_state_assertions([_steps('''
        def assert_item_count(basket_page, count):
            names = basket_page.item_names()
            assert len(names) == count, f"Expected exactly {count}, got {names}"
    ''')], project)

    assert len(errors) == 1
    assert "basket_page" in errors[0]
    assert "'basket'" in errors[0], "name the page whose state persists"


def test_an_emptiness_assertion_is_absolute(project):
    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty(), "Expected it to be empty"
    ''')], project)
    assert len(errors) == 1


def test_the_rejection_offers_only_remedies_this_application_can_do(project):
    """The message is guidance, and guidance that cannot be followed gets
    approximated.

    It used to name "register a fresh account" first, always. In an
    application whose inventory holds no password field and no
    account-details form, that cannot be written - and a run that tried
    invented a password, never submitted it, and failed at login with "No
    session after logging in". A whole story, lost to an instruction that
    could not be carried out.

    The options are now assembled from `_starting_state`, so an application
    that declares no way to establish a clean start is told to assert
    relatively, which it can always do.
    """
    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    message = errors[0].lower()

    assert "relative" in message, "always available, so always offered"
    assert "wait" in message, (
        "say that waiting will not help - the previous failure's remedy is "
        "the obvious wrong turn here"
    )

    # This fixture project declares no `_starting_state` at all, so the
    # framework's own fresh-identity fixture is the only thing on offer -
    # which is the right default for an application that has not thought
    # about this yet.
    assert "unique_username" in message
    assert "clear the state" not in message, (
        "nothing declares an establishing call here, so offering one would "
        "send the model looking for a method that does not exist"
    )


def test_a_remedy_the_application_cannot_do_is_not_offered(project, tmp_path):
    """Break the thing the guard guards.

    An application declaring an EMPTY fresh_identity_fixtures list is saying
    "there is no way to register here". The default used to be unioned in
    regardless, overruling it.
    """
    import json

    path = tmp_path / "app_inventory" / "app.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_starting_state"] = {"fresh_identity_fixtures": [],
                               "establishing_calls": ["remove_all_items"]}
    path.write_text(json.dumps(data), encoding="utf-8")

    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], tmp_path)

    message = errors[0]
    assert "remove_all_items" in message, "offer what the application CAN do"
    assert "unique_username" not in message, (
        "an explicit empty list means there is no way to register here; "
        "offering it anyway is how a story ends up writing half a "
        "registration flow"
    )


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# Every one of these is legitimate code. A validator that rejected them would
# make relative assertions impossible to write and would be turned off.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("assertion", [
    "assert item_name in basket_page.item_names()",
    "assert item_name not in basket_page.item_names()",
    "assert any(item_name in row for row in basket_page.rows())",
])
def test_relative_assertions_are_allowed(project, assertion):
    errors = validate_persistent_state_assertions([_steps(f'''
        def assert_state(basket_page, item_name):
            {assertion}
    ''')], project)
    assert errors == [], f"{assertion!r} holds whatever the state started as"


def test_a_scenario_that_clears_the_state_may_assert_absolutely(project):
    assert validate_persistent_state_assertions([_steps('''
        def given_empty(basket_page):
            basket_page.remove_all_items()

        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project) == []


def test_a_scenario_that_registers_its_own_account_may_assert_absolutely(project):
    assert validate_persistent_state_assertions([_steps('''
        def given_fresh(signup_page, unique_username):
            signup_page.register(unique_username)

        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project) == []


def test_the_assertion_is_not_read_as_its_own_remedy(project):
    """`is_empty` contains the word 'empty'. An earlier draft matched it as a
    state-clearing call and skipped the file - passing the exact code it was
    written to stop. Only a call made for its EFFECT counts."""
    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    assert len(errors) == 1


def test_a_page_without_persistent_state_is_untouched(project):
    assert validate_persistent_state_assertions([_steps('''
        def assert_results(listing_page):
            assert listing_page.result_count() == 3
    ''')], project) == []


def test_an_application_declaring_nothing_persistent_is_untouched(tmp_path):
    """The default. Adding this check must not change any application that has
    not opted into it."""
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "T",
        "pages": {"basket": {"url": "/b", "page_object_class": "BasketPage",
                             "elements": {}}},
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: T\n  inventory_file: app_inventory/app.json\n",
        encoding="utf-8")

    assert validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], tmp_path) == []


def test_page_objects_are_not_judged_only_step_definitions(project):
    """A page object comparing counts internally is its own business."""
    assert validate_persistent_state_assertions([SimpleNamespace(
        file_path="pages/basket_page.py",
        content=textwrap.dedent('''
            class BasketPage:
                def is_empty(self) -> bool:
                    return len(self.item_names()) == 0
        '''),
    )], project) == []


def test_an_unreadable_inventory_disables_the_check(tmp_path):
    """A validator must never be the reason a run dies."""
    assert validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], tmp_path) == []


def test_the_mapping_survives_a_page_object_that_was_not_regenerated(project):
    """ai-update regenerates step definitions without their page objects. A
    check that only read generated files would find no mapping and silently
    pass - so the fixture name comes from the inventory's own
    page_object_class."""
    errors = validate_persistent_state_assertions([_steps('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    assert len(errors) == 1, "no page object was supplied, and it still fired"


# =========================================================================
# A STEP NAME IS A CLAIM, NOT EVIDENCE
#
# The check asked "does this file establish its own starting state?" by
# searching the source for the word `register`. A step declared
#
#     @given("a newly registered account")
#
# contains it. Behind that name the step called a helper whose own docstring
# reads "This does NOT create the account", and then signed in as the shared
# role - so the scenario claimed a fresh account, used a shared one, and
# asserted the collection was empty. It passed on a run where the leftovers
# happened to be gone, which is worse than failing.
#
# The reviewer caught it by reading the page object. This check had read a
# label.
#
# The second attempt guessed from CALL names instead - anything matching
# register|signup|create_account. `begin_signup` matches. Same mistake, one
# layer down: a name that describes an intention is not a description of
# behaviour, wherever the name happens to sit.
#
# So the rules are DECLARED, in the inventory, beside the pages they concern.
# =========================================================================

def _flow(body: str):
    import textwrap
    from types import SimpleNamespace
    return SimpleNamespace(file_path="tests/step_defs/test_flow.py",
                           content=textwrap.dedent(body))


def test_a_step_named_after_registering_is_not_evidence_of_registering(project):
    """The exact scenario that shipped."""
    errors = validate_persistent_state_assertions([_flow('''
        @given("a newly registered account")
        def given_fresh(login_page, base_url):
            account_page.begin_signup("QA User", "qa@example.test")

        @when("I log in as the new account")
        def do_login(account_page, credentials):
            account_page.sign_in_as(*credentials("shared"))

        @then("the basket should be empty")
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)

    assert errors, (
        "the step is named after registering and does not register - the "
        "check must judge what the code does, not what the step calls itself"
    )


def test_a_call_named_after_signing_up_is_not_evidence_either(project):
    """Break the thing the guard guards, from the other side.

    The second draft matched call names against register|signup|... , and
    `begin_signup` matched. A partial flow with a promising name is exactly
    the case this check exists for.
    """
    errors = validate_persistent_state_assertions([_flow('''
        @given("a fresh account")
        def given_fresh(login_page):
            account_page.begin_signup("QA", "qa@example.test")

        @then("the basket should be empty")
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)

    assert errors, "begin_signup does not create an account; its name says it does"


def test_a_declared_establishing_call_is_accepted(project, tmp_path):
    """What the inventory names IS evidence - somebody declared it deliberately,
    in the file where app knowledge belongs."""
    import json

    path = tmp_path / "app_inventory" / "app.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_starting_state"] = {"establishing_calls": ["remove_all_items"]}
    path.write_text(json.dumps(data), encoding="utf-8")

    assert validate_persistent_state_assertions([_flow('''
        @given("an empty basket")
        def given_empty(basket_page):
            basket_page.remove_all_items()

        @then("the basket should be empty")
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], tmp_path) == []


def test_the_framework_fixture_still_counts_without_any_declaration(project):
    """unique_username is the one app-agnostic answer: it yields an identity
    nothing has used. It must work with no inventory block at all."""
    assert validate_persistent_state_assertions([_flow('''
        @given("a newly registered account")
        def given_fresh(signup_page, unique_username):
            signup_page.complete(unique_username)

        @then("the basket should be empty")
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project) == []


# =========================================================================
# A FRESH IDENTITY THAT IS THEN ABANDONED OWNS NOTHING
#
# Third version of this check, third version of one mistake.
#
#   1. it believed a WORD in a step name  - @given("a newly registered account")
#   2. it believed a promising CALL name  - begin_signup(), which does not register
#   3. it believed a fixture being REQUESTED
#
# Each moved closer to behaviour and stopped one step short. The third
# version passed a file that asked for a fresh identity and then signed in
# with the shared account anyway: the new identity was created and discarded,
# the session belonged to the shared account, and the absolute assertion ran
# against whatever the previous run left.
#
# Both halves of that contradiction are DECLARED - the fixtures under
# `_starting_state`, the shared accounts under `test_users` - so this needs no
# guessing about what any name means.
# =========================================================================

def _shared_account_project(tmp_path):
    """A project declaring one persistent page and one shared account."""
    import json

    (tmp_path / "app_inventory").mkdir(exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "Test App",
        "test_users": {"member": "A pre-existing shared account."},
        "_starting_state": {"fresh_identity_fixtures": ["unique_username"],
                            "establishing_calls": ["remove_all_items"]},
        "pages": {"basket": {"url": "/basket", "page_object_class": "BasketPage",
                             "elements": {"rows": "#rows"},
                             "persistent_state": True}},
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Test App\n"
        "  inventory_file: app_inventory/app.json\n", encoding="utf-8")
    return tmp_path


def test_a_fresh_identity_then_a_shared_login_is_rejected(tmp_path):
    """The shape that shipped."""
    root = _shared_account_project(tmp_path)
    errors = validate_persistent_state_assertions([_flow('''
        @given("a newly registered account")
        def given_fresh(account_page, unique_username):
            account_page.begin_signup("QA", unique_username)

        @given("the usual account")
        def shared(account_page, credentials):
            account_page.sign_in_as(*credentials("member"))

        @then("the basket should be empty")
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], root)

    assert errors, "asking for a fresh identity and then not using it owns nothing"
    message = errors[0]
    assert "unique_username" in message, "name the identity that was abandoned"
    assert "'member'" in message, "name the shared account that was used instead"
    assert "SHARED" in message


def test_a_fresh_identity_actually_used_is_accepted(tmp_path):
    """Break the thing the guard guards. Registering properly is the whole
    point of the rule - blocking it would leave no way to satisfy the check."""
    root = _shared_account_project(tmp_path)
    assert validate_persistent_state_assertions([_flow('''
        @given("a newly registered account")
        def given_fresh(account_page, unique_username):
            account_page.complete_registration(unique_username)

        @then("the basket should be empty")
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], root) == []


def test_a_shared_login_with_a_relative_assertion_is_fine(tmp_path):
    """The shared account is not the problem. Asserting ABSOLUTE state on it
    is. A relative assertion holds whatever the state started as."""
    root = _shared_account_project(tmp_path)
    assert validate_persistent_state_assertions([_flow('''
        @given("the usual account")
        def shared(account_page, credentials):
            account_page.sign_in_as(*credentials("member"))

        @then("the item is in the basket")
        def assert_present(basket_page, item_name):
            assert item_name in basket_page.item_names()
    ''')], root) == []


def test_an_application_declaring_no_shared_accounts_is_untouched(project):
    """`test_users` is optional. Without it there is no contradiction to find,
    and the earlier rules must behave exactly as before."""
    assert validate_persistent_state_assertions([_flow('''
        @given("a newly registered account")
        def given_fresh(account_page, unique_username):
            account_page.complete_registration(unique_username)

        @then("the basket should be empty")
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project) == []


# =========================================================================
# AN ABSOLUTE ASSERTION DOES NOT NEED THE WORD `assert`
#
# The check read `assert` statements. A step definition can make the same
# claim without one:
#
#     @then(parsers.parse("... should contain exactly {count:d} rows"))
#     def assert_row_count(some_page, count):
#         some_page.wait_for_row_count(count)          # no `assert` anywhere
#
# The assertion moved into the page object - which is BETTER style, and made
# it invisible to a check looking for the keyword. A run shipped an absolute
# count on persistent state that way, and the reviewer caught what the gate
# existed to catch.
#
# A method counts as an assertion helper by BEHAVIOUR, not by name: its body
# waits for or compares an exact count. `wait_for_row_count` and `expect_two`
# both qualify; a method merely called `check_something` does not. Names are
# claims - that lesson is three entries up this file.
# =========================================================================

def _counting_page_object():
    import textwrap
    from types import SimpleNamespace
    return SimpleNamespace(file_path="pages/basket_page.py",
                           content=textwrap.dedent('''
        from pages.base_page import BasePage


        class BasketPage(BasePage):
            INVENTORY_PAGE = "basket"

            def wait_for_row_count(self, expected: int) -> None:
                self.wait_for_count(self.sel("rows"), expected)

            def item_names(self):
                return self.get_all_texts(self.sel("names"))
    '''))


def test_an_absolute_count_delegated_to_the_page_object_is_caught(project):
    """The shape that shipped."""
    errors = validate_persistent_state_assertions([
        _counting_page_object(),
        _flow('''
            @then(parsers.parse("the basket should hold exactly {count:d} rows"))
            def assert_count(basket_page, count):
                basket_page.wait_for_row_count(count)
        '''),
    ], project)

    assert errors, (
        "the claim is absolute whether or not the word `assert` appears - "
        "moving it into the page object is better style, not an exemption"
    )


def test_a_plain_call_on_the_same_page_is_not_an_assertion(project):
    """Break the thing the guard guards.

    Treating every call on a persistent-state fixture as an assertion would
    reject opening the page, reading it, or clearing it - which is most of
    what a step definition does.
    """
    assert validate_persistent_state_assertions([
        _counting_page_object(),
        _flow('''
            @given("I open the basket")
            def open_basket(basket_page):
                basket_page.item_names()
        '''),
    ], project) == []


def test_the_helper_is_recognised_by_behaviour_not_by_name(project):
    """A method that counts is caught whatever it is called; a method with a
    checking-sounding name that does not count is not."""
    import textwrap
    from types import SimpleNamespace

    oddly_named = SimpleNamespace(file_path="pages/basket_page.py",
                                  content=textwrap.dedent('''
        from pages.base_page import BasePage


        class BasketPage(BasePage):
            INVENTORY_PAGE = "basket"

            def expect_two(self) -> None:
                self.wait_for_count(self.sel("rows"), 2)

            def check_something(self) -> None:
                self.click(self.sel("refresh"))
    '''))

    caught = validate_persistent_state_assertions([oddly_named, _flow('''
        @then("there should be two")
        def assert_two(basket_page):
            basket_page.expect_two()
    ''')], project)
    assert caught, "expect_two() counts, so it asserts, whatever it is named"

    ignored = validate_persistent_state_assertions([oddly_named, _flow('''
        @when("I refresh")
        def refresh(basket_page):
            basket_page.check_something()
    ''')], project)
    assert ignored == [], "a checking-sounding name that does not count is not an assertion"


# =========================================================================
# THE REMEDY MUST BE ONE THE READER CAN CARRY OUT
#
# The repair loop regenerates ONE file. Owning the starting state spans
# three: a Given line in the .feature, a clearing method on the page object,
# and the step definition binding them.
#
# The message led with owning the state anyway. A story spent four repair
# attempts and 3,170 characters of feedback trying to follow it, produced the
# same four errors every time, and was abandoned. The one thing the model
# could actually do - rewrite the assertion in the file in front of it - was
# listed second and framed as the fallback.
#
# "Unsatisfiable guidance gets approximated" is a reading rule here. This is
# the third place it has applied: the prompt, then the error's list of
# options, and now the ORDER of that list. Being reachable is not enough if
# the unreachable one is offered first.
# =========================================================================

def test_the_message_leads_with_what_a_single_file_repair_can_do(project):
    errors = validate_persistent_state_assertions([_flow('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    message = errors[0]

    relative_at = message.lower().find("relative")
    owning_at = message.lower().find("own its starting state")
    assert relative_at != -1, "the achievable remedy must be present"
    if owning_at != -1:
        assert relative_at < owning_at, (
            "the remedy that needs three files is offered before the one that "
            "needs none - a repair regenerates a single file and cannot "
            "deliver the first"
        )


def test_the_multi_file_remedy_says_it_spans_several_files(project):
    """Break the thing the guard guards.

    Reordering alone would still leave a model free to attempt the other
    route. Naming the cost is what makes the choice obvious - and it is the
    fact that decides whether the option exists at all.
    """
    errors = validate_persistent_state_assertions([_flow('''
        def assert_empty(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    message = errors[0].lower()

    if "own its starting state" in message:
        assert "three files" in message or "spans" in message, (
            "say that owning the state needs more than the file being repaired"
        )


# =========================================================================
# BLAME THE FILE THAT CAN BE FIXED
#
# The repair loop regenerates whichever file the error NAMES, and the
# step-def prompt injects the feature file as AUTHORITATIVE. So a step bound
# to `Then the cart should contain exactly 1 product` has no freedom: it must
# implement the sentence it was given, and the sentence is what is wrong.
#
# The error named the step-def file anyway. A story spent four repair
# attempts and 3,170 characters on a file that could not be fixed, produced
# the same errors every time, and was abandoned. The advice was correct and
# addressed to the wrong file.
#
# Naming the feature file is what lets the SCENARIO be rewritten - after
# which the step definition follows, because the coverage check will pull it
# into line on the next pass.
#
# Not every case belongs to the feature. When the Gherkin is neutral and the
# step definition over-asserts of its own accord, the step definition is both
# at fault and fixable, and it keeps the blame.
# =========================================================================

def _feature(body: str = "Feature: F\n"):
    from types import SimpleNamespace
    return SimpleNamespace(file_path="features/f.feature", content=body)


def _bound_step(body: str):
    import textwrap
    from types import SimpleNamespace
    return SimpleNamespace(
        file_path="tests/step_defs/test_f.py",
        content=('from pytest_bdd import scenarios, given, then, parsers\n\n'
                 'scenarios("f.feature")\n\n') + textwrap.dedent(body))


def _blamed(errors):
    return errors[0].split("'")[1] if errors else None


def test_an_absolute_gherkin_phrase_blames_the_feature_file(project):
    """The shape that was abandoned."""
    errors = validate_persistent_state_assertions([_feature(), _bound_step('''
        @then(parsers.parse("the basket should hold exactly {count:d} rows"))
        def a(basket_page, count):
            assert len(basket_page.item_names()) == count
    ''')], project)

    assert _blamed(errors) == "features/f.feature", (
        "the step definition must implement the phrase it is bound to - "
        "reporting against it asks for a fix that file cannot make"
    )
    assert "cannot fix this" in errors[0], "say why the step def is not the place"


def test_an_emptiness_phrase_also_blames_the_feature_file(project):
    errors = validate_persistent_state_assertions([_feature(), _bound_step('''
        @then("the basket should be empty")
        def a(basket_page):
            assert basket_page.is_empty()
    ''')], project)
    assert _blamed(errors) == "features/f.feature"


def test_a_neutral_phrase_keeps_the_blame_on_the_step_definition(project):
    """Break the thing the guard guards.

    Blaming the feature file for everything would send the model rewriting
    scenarios that are perfectly well phrased. When the Gherkin asks for
    something relative and the step definition asserts a count anyway, the
    step definition is both at fault and able to fix itself.

    UPDATED when routing stopped being a guess. Both files are now reported,
    because a phrase list could not decide reliably which one was wrong. The
    concern above is unchanged and still enforced, in two parts: the step
    definition must be told (it is the file that can fix this one), and the
    feature message must give the model explicit permission to leave a
    well-phrased scenario alone.
    """
    errors = validate_persistent_state_assertions([_feature(), _bound_step('''
        @then("the added item is in the basket")
        def a(basket_page):
            assert len(basket_page.item_names()) == 1
    ''')], project)

    blamed = {e.split("'")[1] for e in errors}
    assert "tests/step_defs/test_f.py" in blamed, (
        "the step definition is at fault here and can fix itself - it must "
        "be told, or this case deadlocks the way SCRUM-111 did"
    )

    feature_error = next(e for e in errors if "features/f.feature" in e)
    assert "leave it unchanged" in feature_error, (
        "a well-phrased scenario must not be rewritten just because the step "
        "definition over-asserted - the message has to say so"
    )


def test_a_relative_assertion_is_still_clean(project):
    assert validate_persistent_state_assertions([_feature(), _bound_step('''
        @then("the added item is in the basket")
        def a(basket_page, item_name):
            assert item_name in basket_page.item_names()
    ''')], project) == []


def test_the_feature_must_be_in_the_batch_to_be_blamed(project):
    """A feature file that is not being generated cannot be repaired either,
    so the error stays where something CAN act on it."""
    errors = validate_persistent_state_assertions([_bound_step('''
        @then(parsers.parse("the basket should hold exactly {count:d} rows"))
        def a(basket_page, count):
            assert len(basket_page.item_names()) == count
    ''')], project)

    assert _blamed(errors) == "tests/step_defs/test_f.py", (
        "no feature file in the batch - blaming one would route the repair at "
        "a file that is not there"
    )


# =========================================================================
# WHICH FILE gets told - the routing must not be a guess
#
# THE SAME DEADLOCK, TWICE
#   The step definition must implement the Gherkin phrase it is given. When
#   that phrase claims an exact state, no edit to the step-def file can make
#   the assertion relative, so reporting against it asks a model to fix a
#   file that cannot be fixed. One story spent four attempts and 3,170
#   characters that way.
#
#   The remedy was a regex over the step text: if it "sounds absolute",
#   report the FEATURE instead. It matched one exact phrasing and missed
#   every paraphrase of it - see _PHRASES below, all of which mean the
#   same thing and only the first of which routed. The next story to
#   phrase it differently deadlocked the same way: three attempts,
#   identical error each time.
#
#   A phrase list cannot be completed. So it stopped being load-bearing:
#   when the feature is in the batch, BOTH files are reported and each
#   message goes to the file that can answer it.
# =========================================================================

_FEATURE = SimpleNamespace(
    file_path="features/flow.feature",
    content="Feature: F\n  Scenario: S\n    Then the state is checked\n",
)


def _steps_with_phrase(phrase: str, body: str) -> SimpleNamespace:
    return SimpleNamespace(
        file_path="tests/step_defs/test_flow.py",
        content=textwrap.dedent(f'''
            from pytest_bdd import scenarios, then
            scenarios("../../features/flow.feature")

            @then("{phrase}")
            def assert_state(basket_page):
            {body}
        '''),
    )


_PHRASES = [
    "the basket should be empty",          # the one the old regex matched
    "I should see an empty basket",        # the ones it did not
    "the basket should contain no items",
    "no items should remain in the basket",
    "I should see the empty basket message",
    "the basket should have 0 items",
]


@pytest.mark.parametrize("phrase", _PHRASES)
def test_the_feature_is_always_told_whatever_the_phrasing(project, phrase):
    """The regression. Every one of these deadlocked except the first."""
    errors = validate_persistent_state_assertions(
        [_FEATURE, _steps_with_phrase(phrase, "    assert basket_page.is_empty()")],
        project,
    )
    named = {"feature" if "features/flow.feature" in e else "step_def"
             for e in errors}
    assert "feature" in named, (
        f"{phrase!r} routed only to the step definition, which cannot "
        f"implement anything other than the phrase it was given - that is "
        f"the deadlock this rule exists to prevent"
    )


@pytest.mark.parametrize("phrase", _PHRASES)
def test_the_step_definition_is_told_as_well(project, phrase):
    """Both, not one. If the scenario was fine and the step over-asserted,
    only the step-def message can fix it - and the reverse for the feature.
    Reporting one and stopping is what made the routing a guess that had to
    be right first time."""
    errors = validate_persistent_state_assertions(
        [_FEATURE, _steps_with_phrase(phrase, "    assert basket_page.is_empty()")],
        project,
    )
    named = {"feature" if "features/flow.feature" in e else "step_def"
             for e in errors}
    assert named == {"feature", "step_def"}, f"got {named}"


def test_the_hint_says_which_file_is_the_likely_culprit(project):
    """The regex still earns its keep - as a hint that nothing routes on."""
    def feature_error(phrase):
        errors = validate_persistent_state_assertions(
            [_FEATURE, _steps_with_phrase(phrase, "    assert basket_page.is_empty()")],
            project,
        )
        return next(e for e in errors if "features/flow.feature" in e)

    assert "EXACT claim" in feature_error("the basket should be empty")
    assert "over-asserted" in feature_error("I should see an empty basket")


def test_a_relative_assertion_clears_both_errors(project):
    """Convergence. Once the assertion is relative there is nothing to report,
    so the loop terminates instead of cycling between the two files."""
    errors = validate_persistent_state_assertions(
        [_FEATURE, _steps_with_phrase(
            "the removed item should be gone",
            "    assert name not in basket_page.item_names()")],
        project,
    )
    assert errors == []


def test_without_a_feature_in_the_batch_only_the_step_def_is_told(project):
    """An ai-update regenerates the step definitions against a feature file
    that already exists. There is no feature to report against, and the
    previous behaviour must be untouched."""
    errors = validate_persistent_state_assertions(
        [_steps_with_phrase("the basket should be empty",
                            "    assert basket_page.is_empty()")],
        project,
    )
    assert len(errors) == 1
    assert "features/" not in errors[0]
    assert "tests/step_defs/test_flow.py" in errors[0]


# =========================================================================
# A step must verify the quantity its own sentence names
#
# WHAT SHIPPED, TWICE, IN THE SAME BATCH
#   Two stories reached review with step definitions whose Gherkin promised
#   a count and whose bodies checked a hard-coded name instead. The reviewer
#   caught both. Nothing else did.
#
# WHY IT APPEARED WHEN IT DID
#   The persistent-state check tells a single-file repair to assert
#   RELATIVELY. That is right advice for the BODY and says nothing about the
#   sentence, so the cheapest way to satisfy it is to weaken the body and
#   leave a phrase promising a count nobody checks. The gate went green on a
#   step that verified nothing.
#
#   These two checks now close on each other. On a persistent page the body
#   may not assert the count AND the sentence may not claim one, so the only
#   move left is to change the sentence - which is what the feature error
#   has been asking for the whole time. The convergence test at the bottom
#   is the one that matters: it walks the exact sequence a repair takes and
#   requires it to terminate.
# =========================================================================

from validators.method_resolution_validator import (
    validate_step_claims_are_verified,
)


def _claim_step(phrase: str, body: str, args: str = "basket_page"):
    return SimpleNamespace(
        file_path="tests/step_defs/test_flow.py",
        content=textwrap.dedent(f'''
            from pytest_bdd import scenarios, then, parsers
            scenarios("../../features/flow.feature")

            @then({phrase})
            def assert_state({args}):
            {body}
        '''),
    )


_CLAIM_FEATURE = SimpleNamespace(
    file_path="features/flow.feature",
    content="Feature: F\n  Scenario: S\n    Then the state is checked\n",
)


def test_a_captured_parameter_the_body_never_accepts_is_rejected(project):
    """Runs GREEN today: pytest-bdd injects only what the function declares
    and ignores the rest. So the step is parameterised, behaves identically
    for every value, and a Scenario Outline passes every row."""
    errors = validate_step_claims_are_verified([_CLAIM_FEATURE, _claim_step(
        'parsers.parse("the basket should contain exactly {count:d} items")',
        '    basket_page.wait_for_item("First Item", present=True)',
    )], project)
    assert errors, "an unused capture is invisible at run time - this is the gate"
    assert "count" in errors[0]


def test_a_sentence_promising_a_count_needs_a_body_that_counts(project):
    errors = validate_step_claims_are_verified([_CLAIM_FEATURE, _claim_step(
        '"the basket should show exactly 1 item"',
        '    basket_page.wait_for_item("First Item", present=True)',
    )], project)
    assert errors


def test_a_sentence_promising_emptiness_needs_a_body_that_reads_it(project):
    errors = validate_step_claims_are_verified([_CLAIM_FEATURE, _claim_step(
        '"the basket should be empty"',
        '    basket_page.wait_for_item("First Item", present=False)',
    )], project)
    assert errors


def test_the_sentence_is_blamed_when_the_page_keeps_state(project):
    """Routing is not a style choice. On a persistent page the OTHER check
    forbids asserting the count, so telling the body to assert it would be
    the two validators contradicting each other - the deadlock this pair
    exists to avoid."""
    errors = validate_step_claims_are_verified([_CLAIM_FEATURE, _claim_step(
        '"the basket should be empty"',
        '    basket_page.wait_for_item("First Item", present=False)',
    )], project)
    assert "features/flow.feature" in errors[0], (
        "the body cannot legally assert the count here, so the sentence is "
        "the only thing that can change"
    )


def test_an_ordinary_page_is_told_to_fix_the_body(project):
    """`listing` is not persistent, so asserting the count IS legal and the
    step definition is both at fault and able to fix itself."""
    errors = validate_step_claims_are_verified([_CLAIM_FEATURE, _claim_step(
        '"the listing should show exactly 3 cards"',
        '    listing_page.wait_for_card("First", present=True)',
        args="listing_page",
    )], project)
    assert errors and "tests/step_defs/test_flow.py" in errors[0]


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# A quantity check that fires on ordinary phrasing would make the gate red
# on every pull request, and a gate that is always red gets switched off.
# ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,body,args", [
    # count captured and actually used
    ('parsers.parse("the basket should contain exactly {count:d} items")',
     "    basket_page.assert_row_count(count)", "basket_page, count"),
    # emptiness asserted through the page object
    ('"the basket should be empty"', "    assert basket_page.is_empty()", "basket_page"),
    # a relative phrase with a relative body - the shape the guidance asks for
    ('parsers.parse(\'the basket should contain "{name}"\')',
     "    basket_page.wait_for_item(name, present=True)", "basket_page, name"),
    # "exactly" modifying a THING, not a number
    ('parsers.parse(\'I see exactly the item I added "{name}"\')',
     "    basket_page.wait_for_item(name, present=True)", "basket_page, name"),
    # an action step claims nothing
    ('"I remove the item"', "    basket_page.remove_item(\"X\")", "basket_page"),
])
def test_well_formed_steps_are_not_flagged(project, phrase, body, args):
    assert validate_step_claims_are_verified(
        [_CLAIM_FEATURE, _claim_step(phrase, body, args)], project) == []


def test_the_two_checks_converge_instead_of_ping_ponging(project):
    """The sequence a repair actually walks. If this cycles, the loop burns
    four attempts and the story fails - which is the failure both of these
    checks were built to stop."""
    def totals(phrase, body):
        files = [_CLAIM_FEATURE, _claim_step(phrase, body)]
        return (len(validate_persistent_state_assertions(files, project)),
                len(validate_step_claims_are_verified(files, project)))

    # 1. as generated: absolute phrase, absolute body
    assert totals('"the basket should be empty"',
                  "    assert basket_page.is_empty()")[0] > 0

    # 2. body weakened, sentence left alone - what shipped. Must NOT be clean.
    assert totals('"the basket should be empty"',
                  '    basket_page.wait_for_item("X", present=False)')[1] > 0, (
        "weakening the body while the sentence still promises emptiness is "
        "the escape hatch that let an unverified step through the gate"
    )

    # 3. sentence reworded too - both checks clean, the loop terminates
    assert totals('"the removed item should be gone"',
                  '    basket_page.wait_for_item("X", present=False)') == (0, 0)


# =========================================================================
# The feature file must actually resolve - it never had
#
# WHAT HAPPENED
#   Three separate fixes routed an error to the feature file so the scenario
#   text could be rewritten. All three were inert. _feature_in_batch matched
#   `scenarios("<path>")` with a regex requiring a quote straight after the
#   bracket, but the generation prompt and the committed reference step
#   definition both mandate
#
#       scenarios(str(feature_path("<the feature stem>")))
#
#   so the quote is three tokens away and the string is a bare snake_case
#   name. It resolved to None on every file the framework actually produces.
#   The feature file was never blamed in a real run, every error fell back to
#   the step definition, and a repair loop oscillated between two rules that
#   only the feature file could reconcile - four attempts, then failure.
#
#   Each fix was verified against a literal-path call that the prompt does
#   not allow. That is the mistake this test exists to make impossible: the
#   convention is now READ FROM THE REPO rather than restated here, so a
#   change to either side fails loudly instead of silently doing nothing.
# =========================================================================


def _reference_step_def() -> tuple:
    """(source, feature_stem) for whatever THIS project declares as its
    reference step definition.

    Read from config, never hardcoded. `reference_files` in config.yaml is
    how the framework is pointed at a different application - naming one
    app's file here would make this test pass for that app and silently skip
    or fail for every other.
    """
    root = Path(__file__).resolve().parents[2]
    try:
        from core.app_context import AppContext
        rel = AppContext.load().reference_step_def
    except Exception:                                     # noqa: BLE001
        pytest.skip("no app context configured in this checkout")
    ref = root / rel
    if not ref.is_file():
        pytest.skip(f"reference step definition {rel} not in this checkout")
    return ref.read_text(encoding="utf-8"), ref.stem.removeprefix("test_")


def _balanced_scenarios_calls(text: str) -> list:
    """Every `scenarios(...)` call in `text`, brackets balanced.

    A non-greedy regex stops at the first `)` and truncates
    `scenarios(str(feature_path("x")))` into something unparseable, which
    made this check fail on a prompt that was perfectly correct.
    """
    calls = []
    for m in re.finditer(r"scenarios\(", text):
        depth, i = 0, m.end() - 1
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    calls.append(text[m.start():i + 1])
                    break
            elif text[i] == "\n":
                break
            i += 1
    return calls


def test_feature_resolution_matches_the_real_convention():
    """The committed reference is the contract. If this fails, either the
    convention moved or the resolver did, and every feature-file error has
    silently stopped being delivered."""
    source, stem = _reference_step_def()
    path = f"features/{stem}.feature"
    feature = SimpleNamespace(file_path=path, content="")

    assert _feature_in_batch(source, [feature]) == path, (
        "the resolver cannot read the scenarios() call the reference step "
        "definition actually uses. Every error routed to a feature file is "
        "now silently reported against the step definition instead, where it "
        "cannot be fixed - which is exactly how a repair loop deadlocks."
    )


def test_the_prompt_still_mandates_the_shape_the_resolver_reads():
    """Belt and braces: the prompt is where Agent 2 learns the call."""
    root = Path(__file__).resolve().parents[2]
    prompt = root / "prompts" / "agent2_coder_generate.md"
    if not prompt.is_file():
        pytest.skip("no generation prompt in this checkout")
    text = prompt.read_text(encoding="utf-8")

    quoted = _balanced_scenarios_calls(text)
    assert quoted, "the prompt no longer shows a scenarios() call at all"
    feature = SimpleNamespace(file_path="features/feature_name.feature", content="")
    assert any(
        _feature_in_batch(f'{call}', [feature]) == "features/feature_name.feature"
        for call in quoted
    ), (
        f"none of the scenarios() forms the prompt teaches can be resolved: "
        f"{quoted}. Agent 2 will write one of these and the feature file will "
        f"never be blamed."
    )


@pytest.mark.parametrize("call", [
    'scenarios(str(feature_path("flow")))',      # the mandated form
    'scenarios(feature_path("flow"))',
    'scenarios("flow.feature")',
    'scenarios("../../features/flow.feature")',
    'scenario(str(feature_path("flow")), "S")',
])
def test_every_call_shape_resolves(call):
    feature = SimpleNamespace(file_path="features/flow.feature", content="")
    assert _feature_in_batch(call, [feature]) == "features/flow.feature"


@pytest.mark.parametrize("call", [
    'scenarios(str(feature_path("something_else")))',   # a different feature
    'x = 1',                                            # no scenarios call
    'def (:',                                           # unparseable
])
def test_it_does_not_resolve_what_it_should_not(call):
    """Break the thing the guard guards. Matching too eagerly would blame a
    feature file the step definition does not drive."""
    feature = SimpleNamespace(file_path="features/flow.feature", content="")
    assert _feature_in_batch(call, [feature]) is None


def test_the_persistent_state_error_reaches_the_feature_with_the_real_call(project):
    """End to end, using the convention rather than a convenient literal.
    This is the assertion that would have caught all three inert fixes."""
    step = SimpleNamespace(
        file_path="tests/step_defs/test_flow.py",
        content=textwrap.dedent('''
            from pytest_bdd import scenarios, then
            from config.paths import feature_path
            scenarios(str(feature_path("flow")))

            @then("the basket should be empty")
            def assert_empty(basket_page):
                assert basket_page.is_empty()
        '''),
    )
    errors = validate_persistent_state_assertions([_CLAIM_FEATURE, step], project)
    assert any("features/flow.feature" in e for e in errors), (
        "with the real scenarios() call the feature file must still be "
        "blamed - it never was"
    )


# =========================================================================
# The model was corrected against a name it had never been shown
#
# THE WHOLE CHAIN, AND WHY IT LOOKED LIKE THE MODEL REFUSING TO COMPLY
#   1. The prompt told Agent 2 that owning a starting state needs "a clearing
#      method on the page object", and never said what it is called.
#   2. The name lives under `_starting_state.establishing_calls`, and
#      filter_inventory_by_components strips every top-level `_` key before
#      the inventory is sent. The one block naming it was deleted on the way
#      in.
#   3. The app-context module pointed AT that block by name - a pointer to
#      something that had been removed.
#   4. The validator demanded exactly those names, and every repair remedy
#      printed them.
#
#   So the model was asked for a method whose required name it had never
#   seen, corrected against that name, and could not comply. Story after
#   story failed, and each log read like a model ignoring an available fix.
#
#   Stripping `_` keys is right; they are notes to a human. The mistake was
#   that one of them had quietly become a CONTRACT. It is now rendered into
#   the prompt as instructions, and enforced here so it cannot be left to
#   guidance again.
#
#   The page object is also the one file a repair can never reach - the loop
#   regenerates the feature and the step definitions only - so if it is not
#   written during generation, the absolute assertion is lost for the run.
# =========================================================================

from validators.method_resolution_validator import (
    validate_persistent_pages_can_be_cleared,
)


def _bookworm(tmp_path, starting_state, persistent=True):
    """A SECOND application, built here rather than borrowed from the one
    under test. Anything that only works for the configured app is not a
    framework fix."""
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "config").mkdir()
    inventory = {"app_name": "Bookworm Library", "pages": {
        "loans": {"url": "/loans", "page_object_class": "LoansPage",
                  "elements": {"rows": "#r"},
                  **({"persistent_state": True} if persistent else {})}}}
    if starting_state is not None:
        inventory["_starting_state"] = starting_state
    (tmp_path / "app_inventory" / "a.json").write_text(
        json.dumps(inventory), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Bookworm Library\n"
        "  inventory_file: app_inventory/a.json\n", encoding="utf-8")
    return tmp_path


def _loans_page(methods: str):
    return SimpleNamespace(
        file_path="pages/loans_page.py",
        content="class LoansPage:\n" + methods)


def test_the_prompt_states_the_required_name(tmp_path):
    """The regression. The name was never in the model's context."""
    from agents.agent2_coder import _build_starting_state_block

    root = _bookworm(tmp_path, {"fresh_identity_fixtures": [],
                                "establishing_calls": ["return_all_loans"]})
    block = _build_starting_state_block(root)
    assert "return_all_loans" in block, (
        "the model is asked for this method by name at the gate; it has to "
        "be told the name before it writes the file"
    )
    assert "LoansPage" in block, "and which page object must carry it"


def test_the_prompt_names_the_fresh_identity_fixture_when_there_is_one(tmp_path):
    from agents.agent2_coder import _build_starting_state_block

    root = _bookworm(tmp_path, {"fresh_identity_fixtures": ["unique_member"],
                                "establishing_calls": ["return_all_loans"]})
    assert "unique_member" in _build_starting_state_block(root)


def test_the_prompt_says_so_when_there_is_no_fresh_identity(tmp_path):
    """Silence here is what produced steps claiming to register an account in
    an application that cannot."""
    from agents.agent2_coder import _build_starting_state_block

    root = _bookworm(tmp_path, {"fresh_identity_fixtures": [],
                                "establishing_calls": ["return_all_loans"]})
    assert "NO fresh-identity fixture" in _build_starting_state_block(root)


def test_a_persistent_page_object_without_the_call_is_rejected(tmp_path):
    root = _bookworm(tmp_path, {"establishing_calls": ["return_all_loans"]})
    errors = validate_persistent_pages_can_be_cleared(
        [_loans_page("    def open_loans(self): pass\n")], root)
    assert errors and "return_all_loans" in errors[0]


@pytest.mark.parametrize("method", ["return_all_loans", "clear_loans"])
def test_either_declared_call_satisfies_it(tmp_path, method):
    root = _bookworm(tmp_path, {
        "establishing_calls": ["return_all_loans", "clear_loans"]})
    assert validate_persistent_pages_can_be_cleared(
        [_loans_page(f"    def {method}(self): pass\n")], root) == []


# ─────────────────────────────────────────────────────────────────────────
# Break the thing the guard guards
#
# A check that fires on page objects it has no business touching would make
# the gate red on every story, and a gate that is always red gets removed.
# ─────────────────────────────────────────────────────────────────────────

def test_a_non_persistent_page_object_is_left_alone(tmp_path):
    root = _bookworm(tmp_path, {"establishing_calls": ["return_all_loans"]},
                     persistent=False)
    assert validate_persistent_pages_can_be_cleared(
        [_loans_page("    def open_loans(self): pass\n")], root) == []


def test_an_application_declaring_nothing_is_untouched(tmp_path):
    from agents.agent2_coder import _build_starting_state_block

    root = _bookworm(tmp_path, None)
    assert _build_starting_state_block(root) == ""
    assert validate_persistent_pages_can_be_cleared(
        [_loans_page("    pass\n")], root) == []


def test_base_page_is_exempt(tmp_path):
    """BasePage is reserved and shared; it is not any page's owner."""
    root = _bookworm(tmp_path, {"establishing_calls": ["return_all_loans"]})
    assert validate_persistent_pages_can_be_cleared(
        [SimpleNamespace(file_path="pages/base_page.py",
                         content="class LoansPage:\n    pass\n")], root) == []


# =========================================================================
# The remedy must be TRUE at the moment it is read
#
# TWO WAYS IT WAS NOT
#
# 1. IT NAMED A CALL THAT DID NOT EXIST.
#    `_starting_state.establishing_calls` is a declaration of intent. Nothing
#    checked that any page object defines the method. For a whole run the
#    inventory advertised a clearing call, the app context told the generator
#    to use it, every error message named it, and no page object anywhere had
#    it. The model was told to call something that was not there - the exact
#    failure this module already names: unsatisfiable guidance gets
#    approximated.
#
# 2. IT CONTRADICTED THE MESSAGE SENT BESIDE IT.
#    The step-def remedy opened "IF YOU ARE EDITING ONLY THE STEP-DEFINITION
#    FILE - which is the case during a repair". That stopped being true when
#    the feature file became routable: both are now repaired in one pass. So
#    in a single attempt the feature was told "add a Given that clears the
#    state" while the step definition was told owning the state "is not
#    something a single-file repair can deliver". It obeyed the message in
#    front of it, never bound the Given the feature had just grown, and the
#    next attempt reverted the feature. Three rounds of that, then failure.
# =========================================================================

from validators.method_resolution_validator import (
    _available_remedies,
    _resolvable_establishing_calls,
)


def _page(name: str, methods: str):
    return SimpleNamespace(
        file_path=f"pages/{name}.py",
        content=textwrap.dedent(f'''
            class SomePage:
            {methods}
        '''),
    )


def test_a_call_no_page_object_defines_is_not_offered(tmp_path):
    (tmp_path / "pages").mkdir()
    usable = _resolvable_establishing_calls(
        {"clear_the_collection"}, [], tmp_path)
    assert usable == set(), (
        "offering a method nothing defines is how a run spent every attempt "
        "being told to call something that was not there"
    )


def test_a_call_defined_in_the_batch_is_offered(tmp_path):
    (tmp_path / "pages").mkdir()
    usable = _resolvable_establishing_calls(
        {"clear_the_collection"},
        [_page("thing_page", "    def clear_the_collection(self): pass")],
        tmp_path,
    )
    assert usable == {"clear_the_collection"}


def test_a_call_defined_on_disk_is_offered(tmp_path):
    """The committed page object counts. That is the whole point of
    committing one: it is available to every future story."""
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "thing_page.py").write_text(
        "class ThingPage:\n    def clear_the_collection(self):\n        pass\n",
        encoding="utf-8")
    assert _resolvable_establishing_calls(
        {"clear_the_collection"}, [], tmp_path) == {"clear_the_collection"}


def test_the_message_says_declared_but_missing_rather_than_absent(tmp_path):
    """WHY there is nothing to offer changes where the reader should look."""
    text = _available_remedies(
        set(), set(), feature_in_batch=True,
        declared_calls={"clear_the_collection"})
    assert "DECLARES" in text and "no page object defines it" in text
    assert "Do NOT call clear_the_collection()" in text
    assert "`_starting_state` in the inventory is empty" not in text, (
        "saying the inventory declares nothing, when it declares a call that "
        "simply does not exist, sends the reader to the wrong file"
    )


def test_an_empty_declaration_still_reads_as_empty():
    """Break the thing the guard guards: the two cases must stay distinct."""
    text = _available_remedies(set(), set(), feature_in_batch=True,
                               declared_calls=set())
    assert "`_starting_state` in the inventory is empty" in text
    assert "DECLARES" not in text


def test_the_two_messages_of_one_attempt_do_not_contradict():
    """The regression. With the feature in the same batch, the step-def
    remedy must not call the three-file fix undeliverable."""
    text = _available_remedies(
        set(), {"clear_the_collection"}, feature_in_batch=True)
    assert "three-file fix IS available" in text
    assert "not something a single-file repair can deliver" not in text, (
        "the feature is being told to add a clearing Given in this same "
        "attempt; telling the step definition it cannot be done is why the "
        "Given was never bound"
    )


def test_without_the_feature_the_old_advice_is_kept():
    """ai-update regenerates step definitions against a feature already on
    main. There the single-file framing is correct and must survive."""
    text = _available_remedies(
        set(), {"clear_the_collection"}, feature_in_batch=False)
    assert "ONLY THE STEP-DEFINITION FILE" in text
    assert "not something a single-file repair can deliver" in text
    assert "three-file fix IS available" not in text


# =========================================================================
# A declared starting-state method survives regeneration with no caller
#
# WHY THIS IS NOT COVERED BY THE EXISTING REMOVAL CHECK
#   _methods_removed_by_regeneration protects a dropped method only when a
#   COMMITTED step definition still calls it - "nothing calls it, so dropping
#   it is safe". That is right for an ordinary helper.
#
#   It is exactly wrong for a method the inventory names under
#   `_starting_state.establishing_calls`. That method exists so a scenario can
#   own its starting state, and the first scenario to need it has not been
#   written - by definition it has NO caller on the day it is committed. So
#   the next regeneration of its own page object would delete it silently,
#   and every persistent-state remedy would go back to naming a call that
#   does not exist.
#
#   The asset the whole remedy depends on had no protection at all.
# =========================================================================

from validators.method_resolution_validator import (
    _methods_removed_by_regeneration,
)


def _project_with_clearing_method(tmp_path, method: str):
    """A minimal project whose inventory DECLARES `method` and whose page
    object defines it. Built here rather than borrowed from the app under
    test, so this stays true for any application."""
    (tmp_path / "pages").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "Thing", "base_url": "https://example.test",
        "_starting_state": {"fresh_identity_fixtures": [],
                            "establishing_calls": [method]},
        "pages": {"collection": {"url": "/c", "page_object_class": "ThingPage",
                                 "persistent_state": True,
                                 "elements": {"rows": "#r"}}},
    }), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Thing\n"
        "  inventory_file: app_inventory/app.json\n", encoding="utf-8")
    (tmp_path / "pages" / "thing_page.py").write_text(
        f"class ThingPage:\n"
        f"    def {method}(self):\n        pass\n"
        f"    def ordinary_helper(self):\n        pass\n", encoding="utf-8")
    return tmp_path


def _regenerated(content: str):
    return SimpleNamespace(file_path="pages/thing_page.py", content=content)


def test_a_declared_clearing_method_cannot_be_dropped(tmp_path):
    """The regression. No caller exists, and that is the point."""
    root = _project_with_clearing_method(tmp_path, "clear_the_collection")
    errors = _methods_removed_by_regeneration(
        [_regenerated("class ThingPage:\n    def ordinary_helper(self):\n"
                      "        pass\n")], root)
    assert errors, (
        "the method every persistent-state remedy names was deleted by a "
        "regeneration and nothing objected"
    )
    assert "clear_the_collection" in errors[0]
    assert "Nothing calls it YET" in errors[0]


def test_keeping_it_raises_nothing(tmp_path):
    root = _project_with_clearing_method(tmp_path, "clear_the_collection")
    assert _methods_removed_by_regeneration(
        [_regenerated("class ThingPage:\n"
                      "    def clear_the_collection(self):\n        pass\n"
                      "    def ordinary_helper(self):\n        pass\n"
                      "    def added_by_this_story(self):\n        pass\n")],
        root) == []


def test_an_ordinary_uncalled_method_may_still_be_dropped(tmp_path):
    """Break the thing the guard guards.

    Protecting EVERY uncalled method would freeze page objects: a story could
    never remove a helper it had just replaced. Only the declared ones are
    load-bearing without a caller.
    """
    root = _project_with_clearing_method(tmp_path, "clear_the_collection")
    assert _methods_removed_by_regeneration(
        [_regenerated("class ThingPage:\n"
                      "    def clear_the_collection(self):\n        pass\n")],
        root) == [], "ordinary_helper has no caller and no declaration"


def test_an_application_declaring_nothing_is_unaffected(tmp_path):
    """No `_starting_state` at all must behave exactly as before."""
    (tmp_path / "pages").mkdir(); (tmp_path / "config").mkdir()
    (tmp_path / "app_inventory").mkdir()
    (tmp_path / "app_inventory" / "app.json").write_text(json.dumps({
        "app_name": "Thing", "pages": {}}), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text(
        "app_under_test:\n  name: Thing\n"
        "  inventory_file: app_inventory/app.json\n", encoding="utf-8")
    (tmp_path / "pages" / "thing_page.py").write_text(
        "class ThingPage:\n    def anything(self):\n        pass\n",
        encoding="utf-8")
    assert _methods_removed_by_regeneration(
        [_regenerated("class ThingPage:\n    pass\n")], tmp_path) == []