"""Put the Gherkin steps, and the evidence for a failure, into the report.

Two gaps, both from the same cause: allure-pytest reports PYTEST, and this
suite is written in Gherkin.

STEPS.  A scenario arrives in the report as one row - passed or failed, with
a duration. Which of its five steps failed, and how far it got, is nowhere.
For a reader who did not write the test that is the only thing worth knowing,
and for a client it is the difference between "the cart test failed" and "it
logged in, searched and added the product, then failed removing it".

pytest-bdd already announces every step it runs. Nothing was listening.

EVIDENCE.  On failure the framework writes a screenshot, a video, a
Playwright trace and a CAUSE/FIX reading - and none of it reaches Allure.
The reading goes into `report.sections`, which pytest prints and junit.xml
carries and allure-pytest never reads; the files sit on disk under names
nobody following a report will guess.

Both are wiring, not new behaviour. Everything attached here already exists.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:                                                      # pragma: no cover
    import allure
    _ALLURE = True
except Exception:                                         # noqa: BLE001
    _ALLURE = False


# Steps are opened on `before` and closed on `after`, so the context manager
# has to outlive the hook that started it. One per test is enough: pytest-bdd
# runs steps sequentially within a scenario.
_open_step: dict = {}


def _title(step) -> str:
    """`When I search for "a thing"` - the sentence as the feature file wrote it.

    The keyword matters. A reader scanning a failed scenario is looking for
    where the Given/When/Then arc broke, and a bare phrase makes them count.
    """
    keyword = (getattr(step, "keyword", "") or "").strip()
    name = (getattr(step, "name", "") or "").strip()
    return f"{keyword} {name}".strip()


def start_step(request, step) -> None:
    """Open an Allure step for one Gherkin step."""
    if not _ALLURE:
        return
    try:
        key = id(request.node)
        # Defensive: a step left open by an earlier error would nest the rest
        # of the scenario inside it and make the report unreadable.
        _close(key, failed=False)
        context = allure.step(_title(step))
        context.__enter__()
        _open_step[key] = context
    except Exception:                                     # noqa: BLE001
        logger.debug("could not open an Allure step", exc_info=True)


def _close(key, failed: bool, exception: BaseException = None) -> None:
    context = _open_step.pop(key, None)
    if context is None:
        return
    try:
        if failed and exception is not None:
            context.__exit__(type(exception), exception, exception.__traceback__)
        else:
            context.__exit__(None, None, None)
    except Exception:                                     # noqa: BLE001
        logger.debug("could not close an Allure step", exc_info=True)


def end_step(request) -> None:
    """Close the current step as passed."""
    if _ALLURE:
        _close(id(request.node), failed=False)


def fail_step(request, exception) -> None:
    """Close the current step as failed, so the report marks THAT step red.

    This is the whole point: the steps before it stay green, and the report
    shows how far the scenario got before it stopped.
    """
    if _ALLURE:
        _close(id(request.node), failed=True, exception=exception)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
_ATTACHMENTS = (
    (".png", "Screenshot at failure", "PNG"),
    (".webm", "Video of the run", "WEBM"),
    (".zip", "Playwright trace (playwright show-trace)", "ZIP"),
)


def attach_failure_evidence(report, evidence_dir) -> int:
    """Attach whatever the run captured for this failed test.

    Called from the makereport hook, where the framework already decides what
    to keep. The files are named after the test, so they can be found without
    being told about them individually.

    Returns how many attachments were made, so a caller can log it and a test
    can assert on it.
    """
    if not _ALLURE:
        return 0

    attached = 0
    try:
        directory = Path(evidence_dir)
        if not directory.is_dir():
            return 0

        # The reading first: it is the thing worth acting on, and an
        # attachment list is read top-down.
        for name, body in getattr(report, "sections", []):
            if "why this failed" in str(name).lower():
                allure.attach(str(body), name="Why this failed",
                              attachment_type=allure.attachment_type.TEXT)
                attached += 1

        stem = str(getattr(report, "nodeid", "")).split("::")[-1]
        for suffix, title, kind in _ATTACHMENTS:
            for path in sorted(directory.glob(f"*{stem}*{suffix}")):
                allure.attach.file(str(path), name=title,
                                   attachment_type=getattr(
                                       allure.attachment_type, kind, None))
                attached += 1
                break                      # one of each; the newest wins
    except Exception:                                     # noqa: BLE001
        logger.debug("could not attach failure evidence", exc_info=True)
    return attached