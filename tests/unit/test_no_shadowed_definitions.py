"""No module defines the same top-level function or class twice.

14 Nov 2026: RP13 (#487) added a second `_pct` to scripts/build_site.py for
the detection rate (already in percent). Python keeps the last definition,
so every pass rate - a fraction - was printed as '1%' and '0.989529%' on
Latest run, History and the PDF until the owner saw it on his phone. The
unit tests of each helper passed; only a scan of the whole tree finds it.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {".git", ".venv", "venv", "node_modules", "reports", "__pycache__"}


def _top_level_redefinitions(source: str) -> list[tuple[str, int, int]]:
    seen: dict[str, int] = {}
    out = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                out.append((node.name, seen[node.name], node.lineno))
            seen[node.name] = node.lineno
    return out


def test_the_scan_finds_a_redefinition():
    src = "def f():\n    return 1\n\n\ndef g():\n    pass\n\n\ndef f():\n    return 2\n"
    assert _top_level_redefinitions(src) == [("f", 1, 9)]


def test_no_module_redefines_a_top_level_name():
    found = {}
    for path in ROOT.rglob("*.py"):
        if SKIP & set(path.relative_to(ROOT).parts):
            continue
        try:
            dups = _top_level_redefinitions(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if dups:
            found[str(path.relative_to(ROOT))] = dups
    assert not found, f"top-level name defined twice (the last one wins): {found}"


def test_pass_rates_and_shares_print_as_percent():
    from scripts import build_site as bs
    assert bs._pct(0.989529) == "99%" and bs._pct(1.0) == "100%" and bs._pct(None) == "-"
    assert bs._share(66.7) == "66.7%" and bs._share(None) == "-"
