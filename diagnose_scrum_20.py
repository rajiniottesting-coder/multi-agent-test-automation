"""
One-shot diagnostic: what does Jira ACTUALLY say about SCRUM-20?

Run from project root:
    python -m diagnose_scrum_20
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from agents.jira_client import JiraClient


def main():
    jira = JiraClient()
    project_key = os.environ.get("JIRA_PROJECT_KEY", "SCRUM")
    story_key = f"{project_key}-20"

    print("=" * 70)
    print(f"DIAGNOSTIC: what does Jira say about {story_key}?")
    print("=" * 70)

    try:
        issue = jira.client.issue(story_key, fields="status,issuetype,labels,project")
    except Exception as e:
        print(f"FAIL: could not fetch {story_key}: {e}")
        return

    print(f"\n--- Raw field values for {story_key} ---")
    print(f"  project.key  = {issue.fields.project.key!r}")
    print(f"  issuetype    = {issue.fields.issuetype.name!r}")
    print(f"  status.name  = {issue.fields.status.name!r}")
    print(f"  labels       = {issue.fields.labels!r}")
    print()
    print("Compare to Agent 1's JQL clauses:")
    print(f"  project = {project_key!r:25} -> {issue.fields.project.key == project_key}")
    print(f'  issuetype = "Story"                       -> {issue.fields.issuetype.name == "Story"}')
    print(f'  status in ("To Do","In Progress")         -> {issue.fields.status.name in ("To Do", "In Progress")}')
    print(f'  labels = "ai-ready"                       -> {"ai-ready" in issue.fields.labels}')
    print(f'  labels != "ai-processed"                  -> {"ai-processed" not in issue.fields.labels}')
    print(f'  labels != "ai-skip"                       -> {"ai-skip" not in issue.fields.labels}')

    print("\n--- Bisecting: which JQL clause excludes SCRUM-20? ---")
    test_clauses = [
        ("project + key only",
            f'project = {project_key} AND key = {story_key}'),
        ("+ issuetype Story",
            f'project = {project_key} AND key = {story_key} AND issuetype = "Story"'),
        ("+ status in (To Do, In Progress)",
            f'project = {project_key} AND key = {story_key} AND issuetype = "Story" '
            f'AND status in ("To Do", "In Progress")'),
        ("+ labels = ai-ready",
            f'project = {project_key} AND key = {story_key} AND issuetype = "Story" '
            f'AND status in ("To Do", "In Progress") AND labels = "ai-ready"'),
        ("+ labels != ai-processed",
            f'project = {project_key} AND key = {story_key} AND issuetype = "Story" '
            f'AND status in ("To Do", "In Progress") AND labels = "ai-ready" '
            f'AND labels != "ai-processed"'),
        ("+ labels != ai-skip (full Agent 1 filter)",
            f'project = {project_key} AND key = {story_key} AND issuetype = "Story" '
            f'AND status in ("To Do", "In Progress") AND labels = "ai-ready" '
            f'AND labels != "ai-processed" AND labels != "ai-skip"'),
    ]
    last_count = None
    for label, q in test_clauses:
        try:
            count = len(list(jira.client.enhanced_search_issues(q, maxResults=5)))
            marker = ""
            if last_count is not None and count < last_count:
                marker = "  <-- THIS CLAUSE EXCLUDES SCRUM-20"
            print(f"  {label:50} -> {count} result(s){marker}")
            last_count = count
        except Exception as e:
            print(f"  {label:50} -> ERROR: {e}")

    print("\n" + "=" * 70)
    print("DONE - share this output to diagnose.")
    print("=" * 70)


if __name__ == "__main__":
    main()