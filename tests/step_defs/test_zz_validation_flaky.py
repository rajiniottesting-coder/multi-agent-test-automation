"""Throw-away validation test (never merged): fails on its first attempt, passes on the retry."""
import tempfile
from pathlib import Path

from pytest_bdd import scenarios, then

from config.paths import feature_path

scenarios(str(feature_path("zz_validation_flaky")))

_MARK = Path(tempfile.gettempdir()) / "zz_validation_flaky.mark"


@then("the throw-away check passes only on its second attempt")
def passes_only_on_the_retry():
    if not _MARK.exists():
        _MARK.write_text("1", encoding="utf-8")
        assert False, "first attempt fails on purpose (validation E29a)"
