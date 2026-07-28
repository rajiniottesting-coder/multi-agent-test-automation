"""External tool adapters and the Protocols they satisfy.

Two independent axes, each a Protocol plus one adapter per platform:

    tracker.py   + jira_client.py     boards, test cases, status, comments
    repo_host.py + github_client.py   branches, commits, PRs, CI status

Everything provider-specific lives here. If an agent can name a query
language, an issue type or an SDK object, the abstraction has leaked.
"""
