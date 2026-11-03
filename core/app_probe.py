"""Is the application under test up, and serving ITSELF? (the app health probe)

WHY
    On 30 Oct 2026 every one of the 17 tests failed in the nightly run on main:
    the login form, the search box, the product list and the newsletter field
    never appeared, on four different pages. Every page was SERVED (no HTTP
    error, no navigation timeout) - just not the application's content. The
    next night all 17 passed with no change. The run had no way to tell "the
    application was not itself" from "17 tests are broken": more than ten
    failures switched the retry off, and the triage raised ten defects and
    one alert for the other seven.

    A failure says what the TEST saw. Whether the APPLICATION was up is a
    separate question, and this module asks it directly: open a few pages the
    application cannot work without and look for elements that are always
    there. Agent 4 asks it after a run with failures (agent4_runner.yml):
      - not up, after waiting for it - every failure of the run is marked an
        outage (not judged, never a defect), with what the application served
        instead as the evidence;
      - up - the failed tests are run again, and only a test that fails again
        can become a defect (core/defects.py).

WHAT IS CHECKED
    `app_under_test.health_check` in config.yaml lists inventory pages and,
    for each, element keys that are always shown on it (application-specific,
    so it lives in config, never here). Each page is opened with
    BasePage.navigate - the same route, retries and load wait the tests use -
    and each element must be visible. With nothing configured, only the base
    URL is checked: served with a good status. That cannot catch a page served
    without its content, which is why the setting exists.

    Timing and waiting are framework settings (`app_health` in config.yaml,
    core/ops_settings.py).

Generic: no application, page or element name lives here.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_SERVED_TEXT_CHARS = 300


@dataclass
class Check:
    """One page the application cannot work without, and what is always on it."""
    page: str                       # inventory page key, or "(base url)"
    url: str                        # path relative to the base URL
    elements: dict = field(default_factory=dict)   # element key -> selector


def _inventory() -> dict:
    from pages.base_page import BasePage
    return BasePage._inventory() or {}


def _app_config() -> dict:
    try:
        import yaml
        from config.paths import CONFIG_YAML
        data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
        return data.get("app_under_test") or {}
    except Exception as e:                                         # noqa: BLE001
        logger.warning("config.yaml unreadable (%s): only the base URL is checked.", e)
        return {}


def checks(config: Optional[dict] = None, inventory: Optional[dict] = None) -> list:
    """The configured checks, resolved against the inventory.

    Raises ValueError naming the problem when the setting refers to a page or
    an element the inventory does not have, or to a page whose URL needs a
    value (`{id}`): a probe that silently checks less than it was told to is
    worse than none.
    """
    config = _app_config() if config is None else config
    entries = config.get("health_check") or []
    if not entries:
        return [Check(page="(base url)", url="/")]
    if not isinstance(entries, list):
        raise ValueError("app_under_test.health_check must be a list of {page, elements}")
    pages = ((_inventory() if inventory is None else inventory).get("pages") or {})
    out = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("page"):
            raise ValueError(f"app_under_test.health_check entry {entry!r} has no `page`")
        key = str(entry["page"])
        page = pages.get(key)
        if page is None:
            raise ValueError(f"health_check page {key!r} is not in the app inventory "
                             f"(pages: {', '.join(sorted(pages))})")
        url = page.get("url") or "/"
        if "{" in url:
            raise ValueError(f"health_check page {key!r} has a URL that needs a value "
                             f"({url}); choose a page with a fixed URL")
        elements = page.get("elements") or {}
        wanted = entry.get("elements") or []
        missing = [e for e in wanted if e not in elements]
        if missing:
            raise ValueError(f"health_check page {key!r} has no element(s) "
                             f"{', '.join(missing)} in the inventory")
        out.append(Check(page=key, url=url, elements={e: elements[e] for e in wanted}))
    return out


def _served(page) -> dict:
    """What the browser actually shows: the evidence for a person."""
    from core.redaction import redact
    info = {"url": "", "title": "", "text": ""}
    try:
        info["url"] = page.url
    except Exception:                                              # noqa: BLE001
        pass
    try:
        info["title"] = redact(page.title())[:120]
    except Exception:                                              # noqa: BLE001
        pass
    try:
        text = page.evaluate("() => (document.body && document.body.innerText) || ''")
        info["text"] = redact(" ".join(str(text).split()))[:_SERVED_TEXT_CHARS]
    except Exception:                                              # noqa: BLE001
        pass
    return info


def probe_once(page, base_url: str, plan: list, timeout_ms: int) -> dict:
    """Open each checked page in `page` and look for its elements.

    {"available": bool, "problem": str | None, "served": {...} | None,
     "checked": ["page: element, ..."]}. Never raises.
    """
    from pages.base_page import BasePage
    obj = BasePage(page)
    checked = []
    for check in plan:
        target = base_url.rstrip("/") + "/" + check.url.lstrip("/")
        try:
            obj.navigate(target)
        except Exception as e:                                     # noqa: BLE001
            first = (str(e).strip().splitlines() or [type(e).__name__])[0][:300]
            return {"available": False, "checked": checked, "served": _served(page),
                    "problem": f"{check.page} ({target}) did not load: {first}"}
        missing = []
        for key, selector in check.elements.items():
            try:
                obj._locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
            except Exception:                                      # noqa: BLE001
                missing.append(key)
        if missing:
            return {"available": False, "checked": checked, "served": _served(page),
                    "problem": (f"{check.page} ({target}) was served without "
                                f"{', '.join(missing)} - the application is not showing "
                                "its own page")}
        checked.append(f"{check.page}: " + (", ".join(check.elements) or "served"))
    return {"available": True, "checked": checked, "served": None, "problem": None}


def probe(open_page: Callable, base_url: str, plan: list, timeout_ms: int,
          wait_seconds: float, interval_seconds: float,
          sleep: Callable = time.sleep, clock: Callable = time.monotonic) -> dict:
    """Probe until the application is up or `wait_seconds` have passed.

    `open_page()` returns a fresh page (and is closed by the caller's context):
    each attempt starts clean, like a test. A short outage is waited out
    rather than reported; the result says how many attempts it took.
    """
    deadline = clock() + max(0.0, wait_seconds)
    attempt = 0
    while True:
        attempt += 1
        try:
            page = open_page()
            result = probe_once(page, base_url, plan, timeout_ms)
        except Exception as e:                                     # noqa: BLE001
            result = {"available": False, "checked": [], "served": None,
                      "problem": f"the probe could not open a page: {type(e).__name__}: {e}"}
        result["attempts"] = attempt
        if result["available"]:
            if attempt > 1:
                logger.warning("The application is up again (attempt %d).", attempt)
            return result
        logger.warning("Application check %d: %s", attempt, result["problem"])
        if clock() + interval_seconds > deadline:
            return result
        sleep(interval_seconds)


def summary(result: dict) -> str:
    """One paragraph for a log, an alert or a failure note."""
    if result.get("available"):
        tries = result.get("attempts", 1)
        return ("The application is up: " + "; ".join(result.get("checked") or ["served"])
                + (f" (after {tries} checks)" if tries > 1 else "") + ".")
    served = result.get("served") or {}
    shown = ""
    if served:
        shown = (f" The browser was at {served.get('url') or '?'}, titled "
                 f"{served.get('title') or '(none)'!r}, showing: "
                 f"{served.get('text') or '(no text)'!r}.")
    return (f"The application is NOT up after {result.get('attempts', 1)} check(s): "
            f"{result.get('problem')}.{shown}")
