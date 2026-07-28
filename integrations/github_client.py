"""
GitHub client wrapper — handles all GitHub API interactions.
Same Adapter pattern as the tracker: agents never call PyGithub directly.

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

    def find_open_pr_for_story(self, story_id: str,
                               branch_prefix: str = "auto/") -> Optional[dict]:
        """Return an OPEN PR belonging to `story_id` as a PLAIN DICT, or None.

        Returns {"number", "head_ref", "head_sha", "url", "title"}.

        Deliberately NOT a provider object: agents used to read `.number` and
        `.head.ref` off a PyGithub PR, which forced any future GitLab / Azure
        Repos adapter to impersonate PyGithub's object shape. Plain dicts keep
        the boundary honest - every provider returns the same five keys.

        Guards the crash window between open_pull_request() and add_label():
        if the runner dies in there, the story keeps its pre-work labels and
        the next tick would redo the whole story.

        Matches `<prefix><STORY>-...` so it also finds -updateN / -revN
        branches, which belong to the same story.
        """
        want = f"{branch_prefix}{story_id}-"
        try:
            for pr in self.repo.get_pulls(state="open"):
                if pr.head.ref.startswith(want):
                    return {
                        "number": pr.number,
                        "head_ref": pr.head.ref,
                        "head_sha": pr.head.sha,
                        "url": pr.html_url,
                        "title": pr.title,
                    }
        except Exception as e:                      # never block on a lookup
            logger.warning(f"Could not check for an existing PR: {e}")
        return None

    def list_open_prs(self, branch_prefix: str = "") -> list[dict]:
        """All open PRs as plain dicts, optionally filtered by branch prefix.

        Same five keys as find_open_pr_for_story. Used by the sweeper, which
        previously iterated raw PyGithub objects.
        """
        out: list[dict] = []
        try:
            for pr in self.repo.get_pulls(state="open"):
                if branch_prefix and not pr.head.ref.startswith(branch_prefix):
                    continue
                out.append({"number": pr.number, "head_ref": pr.head.ref,
                            "head_sha": pr.head.sha, "url": pr.html_url,
                            "title": pr.title})
        except Exception as e:
            logger.warning(f"Could not list open PRs: {e}")
        return out

    def reopen_pull_request(self, pr_number: int) -> None:
        """Close then reopen a PR to re-fire pull_request events.

        The provider-specific way to re-trigger event-driven CI. GitLab would
        implement this differently (or as a no-op plus a pipeline retry), which
        is exactly why it belongs behind the adapter.
        """
        pr = self.repo.get_pull(pr_number)
        pr.edit(state="closed")
        pr.edit(state="open")

    def get_workflow_runs(self, workflow_file: str, branch: str,
                          limit: int = 20) -> list[dict]:
        """Recent CI runs for a workflow on a branch, as plain dicts.

        Returns [{"status", "conclusion", "head_sha"}, ...]. "Workflow" is
        GitHub's word; a GitLab adapter would map this onto pipelines.
        """
        try:
            wf = self.repo.get_workflow(workflow_file)
            return [{"status": r.status, "conclusion": r.conclusion,
                     "head_sha": r.head_sha}
                    for r in wf.get_runs(branch=branch)[:limit]]
        except Exception as e:
            logger.warning(f"Could not read runs for {workflow_file}: {e}")
            return []

    def get_pr_comments(self, pr_number: int) -> list[str]:
        """Comment bodies on a PR."""
        try:
            return [c.body for c in self.repo.get_pull(pr_number).get_issue_comments()]
        except Exception as e:
            logger.warning(f"Could not read comments on PR #{pr_number}: {e}")
            return []

    def delete_branch(self, branch_name: str) -> bool:
        """Delete a branch. Returns True if it was deleted, False otherwise.

        Used to discard a PARTIALLY-WRITTEN branch: files are committed one at a
        time, so a crash mid-loop leaves some files present and others missing.
        Reusing that branch is unsafe - the next run may generate a DIFFERENT
        set of files (a test case was deleted, the plan changed), and any file
        from the abandoned attempt would survive, unvalidated, into the PR.

        Only ever called when NO pull request exists for the branch, so nothing
        under review is destroyed.
        """
        try:
            ref = self.repo.get_git_ref(f"heads/{branch_name}")
            ref.delete()
            logger.info(f"Deleted partially-written branch '{branch_name}'")
            return True
        except Exception as e:
            logger.warning(f"Could not delete branch '{branch_name}': {e}")
            return False

    def branch_exists(self, branch_name: str) -> bool:
        """
        Return True if the named branch exists on the remote, False otherwise.

        Used by Phase 6's regeneration logic to find the lowest unused -revN
        suffix when generating fresh code for an already-coded story.

        Distinct from create_branch's silent-skip behavior: callers may want
        to KNOW whether a branch exists without creating one (e.g., to compute
        the next available revision number).
        """
        try:
            self.repo.get_branch(branch_name)
            return True
        except GithubException as e:
            if e.status == 404:
                return False
            raise

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

    def list_files_in_directory(self, path: str, branch: str = "main") -> list[str]:
        """List file paths in a directory. Returns repo-relative paths.

        Used by orphan-cleanup to find sibling step-def files. Returns
        empty list if the directory does not exist on the branch.
        """
        try:
            contents = self.repo.get_contents(path, ref=branch)
        except Exception as e:
            logger.debug(f"list_files_in_directory({path!r}, {branch!r}) failed: {e}")
            return []
        if not isinstance(contents, list):
            # A single file was returned (path resolved to a file, not dir)
            return [contents.path]
        return [c.path for c in contents if c.type == "file"]

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