# Configuration Reference

> Where every config value lives, what's required, and how to set it for local dev vs CI.

## The Three Layers

The project separates configuration into three intentional layers:

| Layer | What goes here | Where it's stored |
|---|---|---|
| **1. Secrets** | API tokens, passwords, anything that would be a security risk if leaked | `.env` (local) and GitHub Secrets (CI) |
| **2. Non-secret config** | Browser settings, base URLs, agent rules | `config/config.yaml` (committed) |
| **3. Code constants** | Locator strings, schema field names, structural defaults | Source code |

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the design rationale behind this split.

## Required Environment Variables

All of these are **required** — agents fail fast at startup if any are missing.

### For Jira integration (Agents 1, 2, 5)

| Variable | Example value | Purpose |
|---|---|---|
| `JIRA_URL` | `https://yoursite.atlassian.net` | Your Atlassian Cloud URL |
| `JIRA_EMAIL` | `you@example.com` | The account the API token belongs to |
| `JIRA_API_TOKEN` | (token from id.atlassian.com → API tokens) | Auth for Jira API |
| `JIRA_PROJECT_KEY` | `PROJ`, `SCRUM`, `MOBILE`, etc. | Your Jira project's key (no default — must be set) |

### For LLM (all agents)

| Variable | Example value | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | (key from aistudio.google.com/apikey) | Auth for Gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` (default) | Which model to use; optional |

### For GitHub integration (Agents 2, 3)

| Variable | Example value | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | (PAT from github.com/settings/tokens) | Auth for GitHub API. In CI, GitHub Actions auto-provides this. |
| `GITHUB_REPO` | `username/repo-name` | Which repo to operate on. In CI, this is auto-set as `GITHUB_REPOSITORY`. |

### Optional overrides

| Variable | When to use | Default behavior |
|---|---|---|
| `BASE_URL` | Point tests at staging/prod instead of the value in `config.yaml` | Falls back to `config.yaml` |
| `PLAYWRIGHT_HEADLESS` | Force browser headed/headless | Auto: headless in CI, headed locally |
| `JIRA_STORY_KEY` | Manually specify story for Agent 5 | Agent 5 auto-detects from PR branch name |

## Where Each Variable Lives

### Local Development

All variables go in `.env` at the project root. **This file is gitignored** — never commit it.

There's a committed template at `.env.example` showing the format with placeholder values. To get started:

```bash
cp .env.example .env
# Then edit .env with your real values
```

### CI / GitHub Actions

GitHub Actions reads them from **repository secrets**:

```
Repository Settings → Secrets and variables → Actions → New repository secret
```

Each variable in `.env` should have a matching secret in GitHub Actions, with **one exception**:

| Local `.env` name | GitHub Secret name | Why different |
|---|---|---|
| `JIRA_URL` | `JIRA_URL` | Same |
| `JIRA_EMAIL` | `JIRA_EMAIL` | Same |
| `JIRA_API_TOKEN` | `JIRA_API_TOKEN` | Same |
| `JIRA_PROJECT_KEY` | `JIRA_PROJECT_KEY` | Same |
| `GOOGLE_API_KEY` | `GOOGLE_API_KEY` | Same |
| `GITHUB_TOKEN` | _(auto-provided by GitHub Actions, no secret needed)_ | GHA injects this for free |
| `GITHUB_REPO` | `GH_REPO` | ⚠️ GitHub reserves the `GITHUB_*` prefix for system secrets, so we use `GH_REPO` and the workflow YAML maps it back to the `GITHUB_REPO` env var the Python code expects |

The GitHub Secret remap for `GH_REPO → GITHUB_REPO` happens in the workflow YAML:

```yaml
env:
  GITHUB_REPO: ${{ secrets.GH_REPO }}
```

### Agent-by-Agent Requirements

| Agent | Reads | Why |
|---|---|---|
| Agent 1 (Analyst) | `JIRA_*`, `GOOGLE_API_KEY` | Reads stories from Jira, calls Gemini |
| Agent 2 (Coder) | `JIRA_*`, `GOOGLE_API_KEY`, `GITHUB_*` | Reads test cases, calls Gemini, opens PR |
| Agent 3 (Reviewer) | `GITHUB_*`, `GOOGLE_API_KEY` | Reads PR diff, calls Gemini, posts review |
| Agent 4 (Runner) | _(none — runs tests against public SauceDemo)_ | Just executes pytest |
| Agent 5 (Reporter) | `JIRA_*`, `GOOGLE_API_KEY` | Posts results to Jira via Gemini-generated summary |

## Validating Configuration at Startup

The project provides `config.validate_required_env()` for fail-fast checks:

```python
from config import validate_required_env, REQUIRED_JIRA_ENV_VARS, REQUIRED_LLM_ENV_VARS

# At the top of an agent's main():
validate_required_env(REQUIRED_JIRA_ENV_VARS + REQUIRED_LLM_ENV_VARS)
# → MissingEnvVarError if any are unset, with a clear message naming all missing vars at once
```

`JiraClient.__init__()` also validates its own required vars, so a missing `JIRA_*` value will be caught when the client is first instantiated.

## Switching Jira Project Keys

The system is **prefix-agnostic** — switching from one Jira project to another is a one-line change:

```diff
# In .env (local) or as a GitHub Secret (CI):
- JIRA_PROJECT_KEY=SCRUM
+ JIRA_PROJECT_KEY=PROD
```

After the switch:
- Agent 1 will look for stories in the new project
- Agent 2 will create branches like `auto/PROD-123-feature` (using whatever key is in the input story)
- Agent 5 will parse `PROD-123` from the branch name automatically

No code changes needed.

See [`BRANCH_NAMING.md`](BRANCH_NAMING.md) for the branch convention details.

## Troubleshooting

### "Missing required environment variable(s)"

You're seeing this from `validate_required_env()`. Check:
1. Is `.env` present at the project root?
2. Did you copy from `.env.example` and fill in real values?
3. If running in CI, are all the secrets set in repo Settings → Secrets and variables → Actions?

### "Could not determine Jira story key"

Agent 5 hit this. Check:
1. Did you run on a PR? (Agent 5 only runs on PRs)
2. Does the PR branch name contain a Jira key like `PROJ-123`?
3. See [`BRANCH_NAMING.md`](BRANCH_NAMING.md) for the convention.

### "JiraClient: missing required env var(s): JIRA_PROJECT_KEY"

Previously the system silently defaulted to `SCRUM` if this was unset, which masked real misconfigurations. The fix is to set `JIRA_PROJECT_KEY=YOUR_PROJECT` explicitly.

### Tests pass locally but fail in CI

Most common cause: a config value that exists in your local `.env` doesn't exist as a GitHub Secret. Check the Actions log for the specific missing variable name.