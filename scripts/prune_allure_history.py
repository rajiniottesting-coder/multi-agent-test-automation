"""Keep in Allure's history only the tests this run reported.

    python -m scripts.prune_allure_history reports/allure-results

Run after the tests, before `allure generate` (Agent 4 does). Why: see
core.allure_meta.prune_history. Always exits 0 - a history left as it was
never fails a run.
"""
import sys

from core.allure_meta import prune_history


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__.strip().splitlines()[2].strip())
        return 0
    kept, dropped = prune_history(args[0])
    print(f"Allure history: {kept} test(s) kept, {dropped} no longer reported dropped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
