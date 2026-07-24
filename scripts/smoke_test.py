"""
Smoke test: verifies Jira, LLM, and Playwright all work end-to-end.
Run from project root: python scripts/smoke_test.py

PreReq:pip install -r requirements.txt
playwright install chromium

"""
import os
import sys
from dotenv import load_dotenv

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


def test_jira():
    """Verify Jira credentials and project access."""
    from jira import JIRA
    jira = JIRA(
        server=os.getenv("JIRA_URL"),
        basic_auth=(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
    )
    user = jira.myself()
    project = jira.project(os.getenv("JIRA_PROJECT_KEY"))
    issue_types = [it.name for it in project.issueTypes]
    print(f"✅ Jira OK — user: {user['displayName']}, project: {project.name}")
    print(f"   Issue types available: {issue_types}")
    if "Test Case" in issue_types:
        print("   ✅ 'Test Case' issue type is configured")
    else:
        print("   ⚠️  'Test Case' issue type NOT found — needs to be added")

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
        test_jira()
        test_llm()
        test_playwright()
        print("\n" + "=" * 50)
        print("🎉 ALL SYSTEMS GO — setup complete!")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ FAILED: {type(e).__name__}: {e}")
        sys.exit(1)