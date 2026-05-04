"""
Smoke test: verifies Jira, Gemini, and Playwright all work end-to-end.
Run from project root: python scripts/smoke_test.py
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()


def test_env_vars():
    """Make sure required env vars are present."""
    required = ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY", "GOOGLE_API_KEY"]
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

def test_gemini():
    """Verify Gemini API key works."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    response = llm.invoke("Reply with exactly: PONG")
    print(f"✅ Gemini OK — model: {model_name}, response: {response.content.strip()}")


def test_playwright():
    """Verify Playwright can launch a browser and reach the test site."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(os.getenv("BASE_URL", "https://www.saucedemo.com"))
        title = page.title()
        browser.close()
    print(f"✅ Playwright OK — site title: {title}")


if __name__ == "__main__":
    print("=" * 50)
    print("Running smoke tests...")
    print("=" * 50 + "\n")
    try:
        test_env_vars()
        test_jira()
        test_gemini()
        test_playwright()
        print("\n" + "=" * 50)
        print("🎉 ALL SYSTEMS GO — Day 1 setup complete!")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ FAILED: {type(e).__name__}: {e}")
        sys.exit(1)