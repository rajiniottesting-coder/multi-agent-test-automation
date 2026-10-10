"""A local, stateful stand-in for a Jira site - for sandbox flow tests.

The REAL `integrations.jira_client.JiraClient` runs against this: the fake is
installed in place of the `jira` library client, so every adapter code path
(JQL building, link direction, label filtering, owner resolution) executes
exactly as it would in production. Nothing leaves the machine.

What it reproduces from Jira, because the adapter depends on it:
- JQL, for the subset the adapter emits: `project =`, `issuetype =`,
  `status in (...)`, `labels = / != / is EMPTY`, `issue in linkedIssues(K)` and
  `linkedIssues(K, "<description>")`, `( ... OR ... )` groups, `ORDER BY`.
- `labels != "x"` does NOT match an issue with no labels at all (Jira's
  quirk; the adapter adds `labels is EMPTY OR` because of it).
- Link direction: `create_issue_link(type, inwardIssue=A, outwardIssue=B)`
  reads "A <outward description> B". On A the link appears with
  `outwardIssue=B`; on B with `inwardIssue=A`. `linkedIssues(K, d)` follows the
  description as read from K's side.
- Transitions to every status of the simple board workflow.

What it CANNOT prove: that the real site agrees with the direction above.
That is what tests/integration/test_jira_links_live.py is for.
"""
from __future__ import annotations

import itertools
import re
from types import SimpleNamespace
from typing import Optional

LINK_TYPES = {
    "Relates": ("relates to", "relates to"),          # name: (inward, outward)
    "Impacts": ("is impacted by", "impacts"),
    "Blocks": ("is blocked by", "blocks"),
}
STATUSES = ("To Do", "In Progress", "In Review", "Done")


class JIRAError(Exception):
    def __init__(self, status_code: int, text: str):
        super().__init__(text)
        self.status_code, self.text = status_code, text


class FakeJira:
    def __init__(self, project_key: str = "SBX"):
        self.project_key = project_key
        self.issues: dict = {}            # key -> dict
        self.links: dict = {}             # id -> (type, inward, outward)
        self.comments: dict = {}          # key -> [body]
        self._n = itertools.count(1)
        self._link_n = itertools.count(1000)
        self.calls: list = []             # (method, args) audit trail

    # ── seeding ─────────────────────────────────────────────
    def add(self, issuetype: str, summary: str, *, key: Optional[str] = None,
            description: str = "", status: str = "To Do", labels=(),
            components=()) -> str:
        key = key or f"{self.project_key}-{next(self._n)}"
        self.issues[key] = {"key": key, "issuetype": issuetype, "summary": summary,
                            "description": description, "status": status,
                            "labels": list(labels), "components": list(components)}
        return key

    def link(self, type_name: str, inward: str, outward: str) -> str:
        lid = str(next(self._link_n))
        self.links[lid] = (type_name, inward, outward)
        return lid

    # ── issue objects as the jira library returns them ──────
    def _ref(self, key: str):
        d = self.issues[key]
        return SimpleNamespace(key=key, fields=SimpleNamespace(
            summary=d["summary"], status=SimpleNamespace(name=d["status"]),
            issuetype=SimpleNamespace(name=d["issuetype"])))

    def _issue(self, key: str):
        if key not in self.issues:
            raise JIRAError(404, f"Issue {key} does not exist")
        d = self.issues[key]
        links = []
        for lid, (tname, inward, outward) in self.links.items():
            t = SimpleNamespace(name=tname, inward=LINK_TYPES[tname][0],
                                outward=LINK_TYPES[tname][1])
            if inward == key:
                links.append(SimpleNamespace(id=lid, type=t, outwardIssue=self._ref(outward),
                                             inwardIssue=None))
            elif outward == key:
                links.append(SimpleNamespace(id=lid, type=t, inwardIssue=self._ref(inward),
                                             outwardIssue=None))
        comments = SimpleNamespace(comments=[SimpleNamespace(body=b)
                                             for b in self.comments.get(key, [])])
        fake = self

        class _Issue:
            def update(self, fields):
                fake.calls.append(("update", key, dict(fields)))
                for name, value in fields.items():
                    d[name] = list(value) if name == "labels" else value
        issue = _Issue()
        issue.key = key
        issue.fields = SimpleNamespace(
            summary=d["summary"], description=d["description"] or None,
            status=SimpleNamespace(name=d["status"]),
            issuetype=SimpleNamespace(name=d["issuetype"]),
            labels=list(d["labels"]),
            components=[SimpleNamespace(name=c) for c in d["components"]],
            issuelinks=links, comment=comments)
        return issue

    # ── the jira library surface the adapter uses ───────────
    def issue(self, key, fields=None):
        return self._issue(key)

    def create_issue(self, fields: dict):
        self.calls.append(("create_issue", dict(fields)))
        key = self.add(fields["issuetype"]["name"], fields["summary"],
                       description=fields.get("description", ""),
                       labels=fields.get("labels", ()),
                       components=[c["name"] for c in fields.get("components", [])])
        return SimpleNamespace(key=key)

    def create_issue_link(self, type, inwardIssue, outwardIssue):
        self.calls.append(("create_issue_link", type, inwardIssue, outwardIssue))
        if type not in LINK_TYPES:
            raise JIRAError(404, f"No issue link type with name '{type}' found.")
        for k in (inwardIssue, outwardIssue):
            if k not in self.issues:
                raise JIRAError(404, f"Issue {k} does not exist")
        return self.link(type, inwardIssue, outwardIssue)

    def delete_issue_link(self, link_id):
        self.calls.append(("delete_issue_link", link_id))
        self.links.pop(str(link_id))

    def add_comment(self, key, body):
        self.comments.setdefault(key, []).append(body)
        return SimpleNamespace(id=str(len(self.comments[key])))

    def transitions(self, issue):
        return [{"id": str(i), "to": {"name": s}} for i, s in enumerate(STATUSES)]

    def transition_issue(self, issue, transition_id):
        self.issues[issue.key]["status"] = STATUSES[int(transition_id)]

    def sprints(self, board_id, state=None):
        return []

    def enhanced_search_issues(self, jql, maxResults=50, fields=None, **_kw):
        self.calls.append(("search", jql, maxResults))
        keys = [k for k in self.issues if self._match(k, jql)]
        if re.search(r"ORDER BY key ASC", jql, re.I):
            keys.sort(key=lambda k: (k.rsplit("-", 1)[0], int(k.rsplit("-", 1)[1])))
        if maxResults:
            keys = keys[:maxResults]
        return [self._issue(k) for k in keys]

    # ── JQL ─────────────────────────────────────────────────
    def linked(self, key: str, description: Optional[str] = None) -> set:
        out = set()
        for tname, inward, outward in self.links.values():
            in_desc, out_desc = LINK_TYPES[tname]
            if inward == key and (description is None or description.lower() == out_desc):
                out.add(outward)
            if outward == key and (description is None or description.lower() == in_desc):
                out.add(inward)
        return out

    @staticmethod
    def _split(expr: str, sep: str) -> list:
        parts, depth, buf, i = [], 0, "", 0
        while i < len(expr):
            ch = expr[i]
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and expr[i:i + len(sep)].upper() == sep:
                parts.append(buf.strip())
                buf, i = "", i + len(sep)
                continue
            buf += ch
            i += 1
        parts.append(buf.strip())
        return parts

    def _match(self, key: str, jql: str) -> bool:
        jql = re.split(r"\s+ORDER BY\s+", jql, flags=re.I)[0]
        return all(self._clause(key, c) for c in self._split(jql, " AND "))

    def _clause(self, key: str, c: str) -> bool:
        d = self.issues[key]
        c = c.strip()
        if c.startswith("(") and c.endswith(")"):
            return any(self._clause(key, p) for p in self._split(c[1:-1], " OR "))
        if m := re.fullmatch(r'project\s*=\s*"?(\w+)"?', c, re.I):
            return key.startswith(m.group(1) + "-")
        if m := re.fullmatch(r'issuetype\s*=\s*"([^"]+)"', c, re.I):
            return d["issuetype"].lower() == m.group(1).lower()
        if m := re.fullmatch(r"status in \((.+)\)", c, re.I):
            return d["status"] in re.findall(r'"([^"]+)"', m.group(1))
        if re.fullmatch(r"labels is EMPTY", c, re.I):
            return not d["labels"]
        if m := re.fullmatch(r'labels\s*!=\s*"([^"]+)"', c, re.I):
            return bool(d["labels"]) and m.group(1) not in d["labels"]   # Jira's quirk
        if m := re.fullmatch(r'labels\s*=\s*"([^"]+)"', c, re.I):
            return m.group(1) in d["labels"]
        if m := re.fullmatch(r'issue in linkedIssues\("([^"]+)"(?:,\s*"([^"]+)")?\)', c, re.I):
            return key in self.linked(m.group(1), m.group(2))
        if m := re.fullmatch(r'sprint\s*(=|in)\s*.+', c, re.I):
            return True
        raise ValueError(f"FakeJira does not understand JQL clause: {c!r}")


def jira_client_over(fake: FakeJira, monkeypatch, project_key: Optional[str] = None):
    """A real JiraClient whose `client` is `fake`. Patches the env it needs."""
    from integrations.jira_client import JiraClient
    for var, val in (("JIRA_URL", "https://sandbox.invalid"), ("JIRA_EMAIL", "sandbox@invalid"),
                     ("JIRA_API_TOKEN", "sandbox"),
                     ("JIRA_PROJECT_KEY", project_key or fake.project_key)):
        monkeypatch.setenv(var, val)
    jc = JiraClient()
    jc._client = fake
    return jc


class FakeRepoHost:
    """Branches as dicts of {path: content}; `main` is seeded from a folder."""

    def __init__(self, files: dict):
        self.branches = {"main": dict(files)}
        self.prs: list = []

    def create_branch(self, branch_name, from_branch="main"):
        self.branches.setdefault(branch_name, dict(self.branches[from_branch]))

    def branch_exists(self, branch_name):
        return branch_name in self.branches

    def delete_branch(self, branch_name):
        return self.branches.pop(branch_name, None) is not None

    def create_or_update_file(self, path, content, commit_message, branch):
        self.branches[branch][path] = content

    def get_file_content(self, path, branch="main"):
        return self.branches[branch][path]

    def list_files_in_directory(self, path, branch="main"):
        return sorted(p for p in self.branches[branch] if p.startswith(path.rstrip("/") + "/"))

    def open_pull_request(self, title, body, head_branch, base_branch="main"):
        self.prs.append({"number": len(self.prs) + 1, "title": title, "body": body,
                         "head_ref": head_branch, "base": base_branch})
        return f"https://sandbox.invalid/pull/{len(self.prs)}"

    def find_open_pr_for_story(self, story_id, branch_prefix="auto/"):
        return next((p for p in self.prs
                     if p["head_ref"].startswith(f"{branch_prefix}{story_id}-")), None)
