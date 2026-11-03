"""Check that the application under test is up and serving itself (core/app_probe.py).

    python -m scripts.app_probe [--report reports/app_probe.json] [--wait-minutes N]

Agent 4 runs it after a run with failures, before the retry
(agent4_runner.yml). It writes:

  --report          the result as JSON: available, the problem, what was
                    served instead, attempts - read by scripts/finalise_junit.py
                    (--app-probe) and the defect triage, and kept in the run's
                    artifact as evidence
  $GITHUB_OUTPUT    available=true | false | unknown

`unknown` - the setting is wrong, or no browser could start: the probe says
nothing, so the run carries on exactly as without it (the failed tests are
retried, nothing is marked an outage). The exit code is always 0: the probe
informs the run, it never decides it.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("app_probe")


def _base_url() -> str:
    import yaml
    from config.paths import CONFIG_YAML
    data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
    return (os.getenv("BASE_URL") or (data.get("app_under_test") or {}).get("base_url")
            or data.get("base_url") or "")


def _browser_settings() -> dict:
    import yaml
    from config.paths import CONFIG_YAML
    data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
    return data.get("browser") or {}


def run(wait_minutes: float | None = None) -> dict:
    """The probe result, or {"available": "unknown", "problem": ...}."""
    from core import app_probe
    from core.ops_settings import section
    s = section("app_health")
    wait = float(s["wait_minutes"] if wait_minutes is None else wait_minutes) * 60
    try:
        plan = app_probe.checks()
        base = _base_url()
        if not base:
            raise ValueError("no base URL (BASE_URL or app_under_test.base_url)")
    except Exception as e:                                         # noqa: BLE001
        return {"available": "unknown", "problem": f"the health check is not usable: {e}"}
    try:
        from playwright.sync_api import sync_playwright
        from tests.conftest import is_headless_mode, should_block_request
    except Exception as e:                                         # noqa: BLE001
        return {"available": "unknown", "problem": f"no browser: {type(e).__name__}: {e}"}
    browser_cfg = _browser_settings()
    blocked = browser_cfg.get("block_hosts") or []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=is_headless_mode(browser_cfg.get("headless", True)))
        except Exception as e:                                     # noqa: BLE001
            return {"available": "unknown", "problem": f"no browser: {type(e).__name__}: {e}"}
        contexts = []

        def open_page():
            for old in contexts:
                try:
                    old.close()
                except Exception:                                  # noqa: BLE001
                    pass
            contexts.clear()
            context = browser.new_context(viewport=browser_cfg.get("viewport"))
            contexts.append(context)
            if blocked:
                context.route("**/*", lambda route, request: route.abort()
                              if should_block_request(request.url, blocked) else route.continue_())
            page = context.new_page()
            page.set_default_timeout(int(browser_cfg.get("timeout") or 30000))
            return page

        try:
            return app_probe.probe(open_page, base, plan, int(s["element_timeout_ms"]),
                                   wait, float(s["interval_seconds"]))
        finally:
            browser.close()


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", default="reports/app_probe.json")
    ap.add_argument("--wait-minutes", type=float, default=None,
                    help="override app_health.wait_minutes")
    args = ap.parse_args(argv)
    from core.app_probe import summary
    result = run(args.wait_minutes)
    available = result.get("available")
    state = "unknown" if available == "unknown" else ("true" if available else "false")
    text = (f"The application check could not run: {result.get('problem')}"
            if state == "unknown" else summary(result))
    result["summary"] = text
    print(("::warning::" if state != "true" else "") + text)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"available={state}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
