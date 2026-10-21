"""Can a change alter a test result? One rule, used in two places.

- Agent 4 (`.github/workflows/agent4_runner.yml`) skips the browser run on a
  pull request that changes nothing a test reads while it runs.
- Agent 3 then must not treat that run's green conclusion as evidence that a
  predicted test failure is wrong: no app test ran.

The rule lists what is SAFE to skip, not what must run, so an unfamiliar path
runs the tests until someone decides otherwise. Agent prompts and the
application notes (`prompts/`), `docs/` and Markdown are inputs to the agents
or to people - they shape what is generated next, never what existing code
does. Everything else (features, step definitions, page objects, the
inventory, config, conftest, requirements, workflows) can change a result.

Standard library only: the workflow runs this file directly, before any
dependency is installed. Usage: changed paths on stdin, one per line; prints
"true" (run the app tests) or "false".
"""
import re
import sys

NOT_READ_AT_RUNTIME = re.compile(r"^(prompts/|docs/)|\.md$")


def runs_app_tests(paths) -> bool:
    """True unless every path is one no test reads. Fails open: no paths
    (an empty or unreadable list) means run them."""
    paths = [p.strip() for p in (paths or ()) if p and p.strip()]
    if not paths:
        return True
    return any(not NOT_READ_AT_RUNTIME.search(p) for p in paths)


def main() -> int:
    print("true" if runs_app_tests(sys.stdin.read().splitlines()) else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
