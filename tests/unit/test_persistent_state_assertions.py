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

from validators.method_resolution_validator import (
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
    """
    errors = validate_persistent_state_assertions([_feature(), _bound_step('''
        @then("the added item is in the basket")
        def a(basket_page):
            assert len(basket_page.item_names()) == 1
    ''')], project)

    assert _blamed(errors) == "tests/step_defs/test_f.py"


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