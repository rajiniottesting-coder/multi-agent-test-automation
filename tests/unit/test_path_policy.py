"""
Unit tests for the two-tier path policy validator in agent2_coder.

Tier 1 — RESERVED:    immutable reference files (e.g., login.feature)
Tier 2 — EXTENDABLE:  modifiable existing files (e.g., inventory_page.py)
Tier 3 — NEW:         everything else, freshly generated

These tests pin down the exact behavior of validate_paths_against_policy
so future refactors can't silently break the contract that lets Agent 2
extend page objects (which is required for any non-login feature).
"""
import pytest

from agents.app_context import AppContext
from agents.agent2_coder import validate_paths_against_policy


# Stand-ins for the real Pydantic models so we don't depend on Pydantic
# in test code. Only the attributes the validator reads need to be present.
class _FakeFP:
    def __init__(self, file_path: str, is_new_file: bool):
        self.file_path = file_path
        self.is_new_file = is_new_file


class _FakePlan:
    def __init__(self, files):
        self.files_to_create = files


@pytest.fixture
def ctx():
    """A minimal AppContext with both tiers populated.

    We construct directly (not via .load()) to avoid coupling the test
    to whatever's in config.yaml at the time. The dataclass is frozen
    but constructable.
    """
    return AppContext(
        name="TestApp",
        base_url="https://example.com",
        inventory_file="app_inventory/test.json",
        reference_feature="features/ref.feature",
        reference_step_def="tests/step_defs/test_ref.py",
        reference_page_object="pages/ref_page.py",
        reserved_paths=(
            "features/ref.feature",
            "tests/step_defs/test_ref.py",
            "pages/ref_page.py",
        ),
        extendable_paths=(
            "pages/extendable_page.py",
            "pages/base_page.py",
        ),
    )


# ─────────────────────────────────────────────────────────────
# Happy-path: new files in fresh space
# ─────────────────────────────────────────────────────────────

class TestNewFilesAccepted:
    def test_brand_new_feature_file(self, ctx):
        plan = _FakePlan([_FakeFP("features/cart.feature", True)])
        validate_paths_against_policy(plan, ctx)  # no exception

    def test_brand_new_step_def_file(self, ctx):
        plan = _FakePlan([_FakeFP("tests/step_defs/test_cart.py", True)])
        validate_paths_against_policy(plan, ctx)

    def test_brand_new_page_object(self, ctx):
        plan = _FakePlan([_FakeFP("pages/cart_page.py", True)])
        validate_paths_against_policy(plan, ctx)

    def test_multiple_new_files(self, ctx):
        plan = _FakePlan([
            _FakeFP("features/cart.feature", True),
            _FakeFP("tests/step_defs/test_cart.py", True),
            _FakeFP("pages/cart_page.py", True),
        ])
        validate_paths_against_policy(plan, ctx)


# ─────────────────────────────────────────────────────────────
# Reserved tier — must always reject
# ─────────────────────────────────────────────────────────────

class TestReservedRejected:
    def test_reserved_marked_as_new_rejected(self, ctx):
        plan = _FakePlan([_FakeFP("features/ref.feature", True)])
        with pytest.raises(ValueError, match="reserved reference files"):
            validate_paths_against_policy(plan, ctx)

    def test_reserved_marked_as_extending_still_rejected(self, ctx):
        """Even if the LLM marks is_new_file=False, reserved is still off-limits.
        Reserved files are the immutable style baseline — the prompt is
        explicit about that, and the validator mirrors it."""
        plan = _FakePlan([_FakeFP("features/ref.feature", False)])
        with pytest.raises(ValueError, match="reserved reference files"):
            validate_paths_against_policy(plan, ctx)

    def test_each_reserved_file_protected(self, ctx):
        for reserved_path in ctx.reserved_paths:
            plan = _FakePlan([_FakeFP(reserved_path, True)])
            with pytest.raises(ValueError, match="reserved reference files"):
                validate_paths_against_policy(plan, ctx)

    def test_normalization_catches_path_variants(self, ctx):
        """Backslash and ./ prefix variants must still be detected."""
        plan = _FakePlan([_FakeFP("./features/ref.feature", True)])
        with pytest.raises(ValueError, match="reserved reference files"):
            validate_paths_against_policy(plan, ctx)


# ─────────────────────────────────────────────────────────────
# Extendable tier — accept iff is_new_file=False
# ─────────────────────────────────────────────────────────────

class TestExtendableHandling:
    def test_extendable_with_is_new_false_accepted(self, ctx):
        """The whole point of the tier — adding methods to a page object."""
        plan = _FakePlan([_FakeFP("pages/extendable_page.py", False)])
        validate_paths_against_policy(plan, ctx)

    def test_extendable_with_is_new_true_rejected(self, ctx):
        """Setting is_new_file=True for an extendable file would wipe
        existing methods. Validator catches this LLM mistake."""
        plan = _FakePlan([_FakeFP("pages/extendable_page.py", True)])
        with pytest.raises(ValueError, match="extendable"):
            validate_paths_against_policy(plan, ctx)

    def test_extending_inventory_for_sort_feature(self, ctx):
        """The exact scenario that blew up on SCRUM-12 in production:
        a sort feature legitimately needs to extend the inventory page."""
        plan = _FakePlan([
            _FakeFP("features/sort.feature", True),
            _FakeFP("tests/step_defs/test_sort.py", True),
            _FakeFP("pages/extendable_page.py", False),  # extending — was blocked before fix
        ])
        validate_paths_against_policy(plan, ctx)


# ─────────────────────────────────────────────────────────────
# Combined / mixed scenarios
# ─────────────────────────────────────────────────────────────

class TestMixedPlans:
    def test_one_violation_aborts_whole_plan(self, ctx):
        """Even one bad entry alongside good ones still fails the plan."""
        plan = _FakePlan([
            _FakeFP("features/cart.feature", True),       # OK
            _FakeFP("features/ref.feature", True),         # BAD (reserved)
        ])
        with pytest.raises(ValueError):
            validate_paths_against_policy(plan, ctx)

    def test_empty_plan_is_valid(self, ctx):
        """Edge case: empty plan doesn't crash."""
        plan = _FakePlan([])
        validate_paths_against_policy(plan, ctx)


# ─────────────────────────────────────────────────────────────
# Apps with no reserved/extendable configured
# ─────────────────────────────────────────────────────────────

class TestAppsWithoutTiers:
    def test_empty_extendable_means_only_brand_new_allowed(self):
        """Apps that don't list any extendable paths should treat all
        page objects as fresh-only. Any existing-file path becomes
        a TIER 3 NEW path with is_new_file=True being fine."""
        ctx = AppContext(
            name="MinimalApp",
            base_url="https://x.com",
            inventory_file="app_inventory/x.json",
            reference_feature="features/ref.feature",
            reference_step_def="tests/step_defs/test_ref.py",
            reference_page_object="pages/ref_page.py",
            reserved_paths=("features/ref.feature",),
            extendable_paths=(),  # empty
        )
        # No extendable list — any new path is fine
        plan = _FakePlan([_FakeFP("pages/anything.py", True)])
        validate_paths_against_policy(plan, ctx)