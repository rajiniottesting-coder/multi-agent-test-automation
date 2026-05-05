"""
GitHub client wrapper — handles all GitHub API interactions.
Same Adapter pattern as JiraClient: agents never call PyGithub directly.

Day 4: branches, files, pull requests
Day 5: PR reading (changed files, diffs) and comment posting for Agent 3
"""
import os
import logging
import base64
from typing import Optional
from github import Github, Repository, GithubException
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class GitHubClient:
    """Thin wrapper around PyGithub, scoped to our project repo."""

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        self.repo_full_name = os.getenv("GITHUB_REPO")
        if not self.token or not self.repo_full_name:
            raise RuntimeError("GITHUB_TOKEN and GITHUB_REPO must be set in .env")
        self._client: Optional[Github] = None
        self._repo: Optional[Repository.Repository] = None

    @property
    def client(self) -> Github:
        if self._client is None:
            self._client = Github(self.token)
        return self._client

    @property
    def repo(self) -> Repository.Repository:
        if self._repo is None:
            self._repo = self.client.get_repo(self.repo_full_name)
        return self._repo

    # ─────────────────────────────────────────────────────────
    # Branch operations
    # ─────────────────────────────────────────────────────────

    def create_branch(self, branch_name: str, from_branch: str = "main") -> None:
        """Create a new branch from another (default: main). Idempotent — skips if exists."""
        try:
            existing = self.repo.get_branch(branch_name)
            logger.info(f"Branch '{branch_name}' already exists at {existing.commit.sha[:7]}")
            return
        except GithubException as e:
            if e.status != 404:
                raise

        source = self.repo.get_branch(from_branch)
        ref = f"refs/heads/{branch_name}"
        self.repo.create_git_ref(ref=ref, sha=source.commit.sha)
        logger.info(f"Created branch '{branch_name}' from {from_branch} ({source.commit.sha[:7]})")

    # ─────────────────────────────────────────────────────────
    # File operations
    # ─────────────────────────────────────────────────────────

    def create_or_update_file(
        self,
        path: str,
        content: str,
        commit_message: str,
        branch: str,
    ) -> None:
        """Create a new file or update an existing one on the given branch."""
        try:
            existing = self.repo.get_contents(path, ref=branch)
            self.repo.update_file(
                path=path,
                message=commit_message,
                content=content,
                sha=existing.sha,
                branch=branch,
            )
            logger.info(f"Updated {path} on {branch}")
        except GithubException as e:
            if e.status == 404:
                self.repo.create_file(
                    path=path,
                    message=commit_message,
                    content=content,
                    branch=branch,
                )
                logger.info(f"Created {path} on {branch}")
            else:
                raise

    def get_file_content(self, path: str, branch: str = "main") -> str:
        """Read a file's content from the repo."""
        contents = self.repo.get_contents(path, ref=branch)
        return base64.b64decode(contents.content).decode("utf-8")

    # ─────────────────────────────────────────────────────────
    # Pull request operations
    # ─────────────────────────────────────────────────────────

    def open_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> str:
        """Open a PR. Returns the PR URL."""
        existing_prs = self.repo.get_pulls(state="open", head=f"{self.repo.owner.login}:{head_branch}")
        for pr in existing_prs:
            logger.warning(f"PR already exists for branch '{head_branch}': #{pr.number}")
            return pr.html_url

        pr = self.repo.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch,
        )
        logger.info(f"Opened PR #{pr.number}: {pr.html_url}")
        return pr.html_url

    # ─────────────────────────────────────────────────────────
    # PR reading (Day 5 — for Agent 3)
    # ─────────────────────────────────────────────────────────

    def get_pull_request(self, pr_number: int):
        """Fetch a PR by number. Returns the PyGithub PullRequest object."""
        return self.repo.get_pull(pr_number)

    def get_pr_metadata(self, pr_number: int) -> dict:
        """Get high-level PR info: branch, title, body, author, state."""
        pr = self.get_pull_request(pr_number)
        return {
            "number": pr.number,
            "title": pr.title,
            "body": pr.body or "",
            "head_branch": pr.head.ref,
            "base_branch": pr.base.ref,
            "state": pr.state,
            "author": pr.user.login,
            "url": pr.html_url,
        }

    def get_pr_changed_files(self, pr_number: int) -> list[dict]:
        """List files changed in a PR with their patch (diff) text.

        Returns a list of dicts with keys:
          - filename: project-relative path
          - status: "added", "modified", "removed", "renamed"
          - additions: int (lines added)
          - deletions: int (lines deleted)
          - patch: str (the diff hunk; may be None for binary files)
          - content: str (full file content at the PR's head)
        """
        pr = self.get_pull_request(pr_number)
        files = []
        for f in pr.get_files():
            file_info = {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch,  # may be None for binary or very large files
                "content": None,
            }
            # Fetch full content of the file at the PR's head branch (only for non-removed files)
            if f.status != "removed":
                try:
                    file_info["content"] = self.get_file_content(f.filename, branch=pr.head.ref)
                except GithubException as e:
                    logger.warning(f"Could not fetch content for {f.filename}: {e}")
            files.append(file_info)
        logger.info(f"PR #{pr_number}: {len(files)} changed files")
        return files

    # ─────────────────────────────────────────────────────────
    # PR commenting (Day 5 — for Agent 3 to post review)
    # ─────────────────────────────────────────────────────────

    def post_pr_comment(self, pr_number: int, body: str) -> str:
        """Post a comment on the PR conversation. Returns the comment URL.

        Note: this is a regular issue comment, not a review comment.
        Review comments require the line number on a specific diff position
        which is more complex. For Agent 3, a top-level conversation comment
        with markdown formatting is sufficient and clearer.
        """
        pr = self.get_pull_request(pr_number)
        comment = pr.create_issue_comment(body)
        logger.info(f"Posted comment on PR #{pr_number}: {comment.html_url}")
        return comment.html_url