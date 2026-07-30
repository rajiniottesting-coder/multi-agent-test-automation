"""
Smoke test: verifies Jira, LLM, and Playwright all work end-to-end.

Run from the project root, either way:
    python -m scripts.smoke_test      (preferred - matches the other scripts)
    python scripts/smoke_test.py      (also works, see sys.path note below)

PreReq:pip install -r requirements.txt
playwright install chromium

"""
import os
import sys
from pathlib import Path

# Make the project root importable regardless of how this script is invoked.
#
# `python -m scripts.smoke_test` puts the CURRENT DIRECTORY on sys.path, so
# `from integrations...` resolves. `python scripts/smoke_test.py` instead puts
# scripts/ on sys.path[0], and the framework imports below fail with
# ModuleNotFoundError: No module named 'integrations'.
#
# Inserting the root explicitly makes both invocations work. Guarded against
# duplicates so re-running in the same interpreter is a no-op.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from dotenv import load_dotenv  # noqa: E402  (after the sys.path fix above)

load_dotenv()


def test_env_vars():
    """Make sure required env vars are present."""
    required = ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY", "OPENAI_API_KEY"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"❌ Missing env vars: {missing}")
        print("   Check your .env file.")
        sys.exit(1)
    print("✅ Env vars OK")


def test_tracker():
    """Verify the CONFIGURED tracker is reachable and usable.

    Goes through get_tracker() rather than importing a Jira client directly, so
    a client running on Xray / Azure DevOps / TestRail gets their own adapter
    smoke-tested instead of a hardcoded Jira check that could never pass.

    Probes only Protocol operations, so it works against any adapter.
    """
    from integrations.tracker import get_tracker

    tracker = get_tracker()
    name = type(tracker).__name__
    print(f"✅ Tracker adapter loaded: {name} (project: {tracker.project_key})")

    # A read that every tracker must support. An empty result is fine - it
    # proves auth and the query path work; it does not require open work.
    try:
        selection = {"issue_type": "Story", "required_labels": [], "excluded_labels": []}
        stories = tracker.find_stories_to_process(selection)
        print(f"   ✅ Read access OK — selection query returned {len(stories)} story(ies)")
    except Exception as e:
        print(f"   ❌ Read FAILED: {type(e).__name__}: {e}")
        print("      Check credentials and that the project/board exists.")
        raise

    # Adapter-specific extras: only meaningful for the Jira adapter, so they are
    # probed defensively rather than assumed.
    if hasattr(tracker, "client") and hasattr(tracker, "project_key"):
        try:
            project = tracker.client.project(tracker.project_key)
            issue_types = [it.name for it in project.issueTypes]
            print(f"   Issue types available: {issue_types}")
            if "Test Case" in issue_types:
                print("   ✅ 'Test Case' issue type is configured")
            else:
                print("   ⚠️  'Test Case' issue type NOT found — needs to be added")
        except Exception:
            pass          # non-Jira adapter, or no issue-type concept


def test_llm():
    """Verify LLM API key and endpoint work."""
    from langchain_openai import ChatOpenAI
    model_name = os.getenv("LLM_MODEL", "claude-opus-4-6")
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    llm = ChatOpenAI(
        model=model_name,
        temperature=0,
        api_key=api_key,
        base_url=api_base,
    )
    response = llm.invoke("Reply with exactly: PONG")
    print(f"✅ LLM OK — model: {model_name}, response: {response.content.strip()}")


def _app_base_url() -> str:
    """Resolve the app under test's URL. Priority: BASE_URL env >
    config.yaml app_under_test.base_url. App-agnostic by design —
    no application URL is hardcoded in the framework."""
    if os.getenv("BASE_URL"):
        return os.getenv("BASE_URL")
    import yaml
    from pathlib import Path
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    url = (cfg.get("app_under_test") or {}).get("base_url")
    if not url:
        print("\u274c No BASE_URL env var and no app_under_test.base_url in config.yaml")
        sys.exit(1)
    return url


def test_playwright():
    """Verify Playwright can launch a browser and reach the app under test."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(_app_base_url())
        title = page.title()
        browser.close()
    print(f"✅ Playwright OK — site title: {title!r}")


if __name__ == "__main__":
    print("=" * 50)
    print("Running smoke tests...")
    print("=" * 50 + "\n")
    try:
        test_env_vars()
        test_tracker()
        test_llm()
        test_playwright()
        print("\n" + "=" * 50)
        print("🎉 ALL SYSTEMS GO — setup complete!")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ FAILED: {type(e).__name__}: {e}")
        sys.exit(1)