"""An extended page object keeps every method it already had.

A committed page object is a contract: other stories' step definitions call
its methods. When a later story extends the file, a method that disappears or
changes its parameters breaks those other tests - and nothing in generation
would notice, because the broken callers are not part of this story's files.
Only the full test run would, after the pull request is open.

This check compares each generated page object with the version committed in
the repository (the working tree Agent 2 runs on is main) and reports every
public method that was removed or whose existing parameters changed. Adding
methods is always fine; adding a parameter is fine only at the end and with a
default, so every existing call still works.

Errors use the shared `<type> error in '<path>':` format, so the repair loop
regenerates the page object with this feedback, and the final gate refuses
the run if a method is still missing.
"""
from __future__ import annotations

import ast
from pathlib import Path

ERROR_PREFIX = "Removed method error"


Signature = list[tuple[str, bool]]          # [(parameter name, has a default)]


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Signature:
    """Parameters without self/cls, each with whether it has a default."""
    args = fn.args
    positional = args.posonlyargs + args.args
    first_default = len(positional) - len(args.defaults)
    params = [(a.arg, i >= first_default) for i, a in enumerate(positional)]
    params += [(a.arg, d is not None) for a, d in zip(args.kwonlyargs, args.kw_defaults)]
    if params and params[0][0] in ("self", "cls"):
        params = params[1:]
    return params


def _public_methods(source: str) -> dict[str, dict[str, Signature]] | None:
    """{class: {method: signature}} for public methods, or None if unparseable."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    out: dict[str, dict[str, Signature]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            out[node.name] = {
                item.name: _signature(item)
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not item.name.startswith("_")
            }
    return out


def _names(sig: Signature) -> list[str]:
    return [name for name, _default in sig]


def _still_compatible(old: Signature, new: Signature) -> bool:
    """Every existing call still works: the old parameters come first, in the
    same order, and every parameter added after them has a default."""
    if _names(new)[:len(old)] != _names(old):
        return False
    return all(has_default for _name, has_default in new[len(old):])


def _is_page_object(path: str) -> bool:
    name = Path(path).name
    return (path.replace("\\", "/").startswith("pages/") and name.endswith("_page.py")
            and not name.endswith("base_page.py"))


def validate_extended_page_objects_keep_methods(generated_files, project_root: Path) -> list[str]:
    """One error per committed page object that lost or broke a method."""
    errors: list[str] = []
    for gf in generated_files:
        path = gf.file_path.replace("\\", "/").lstrip("./")
        if not _is_page_object(path):
            continue
        committed = Path(project_root) / path
        if not committed.is_file():
            continue                                  # a genuinely new page object
        before = _public_methods(committed.read_text(encoding="utf-8"))
        after = _public_methods(gf.content or "")
        if before is None or after is None:
            continue                                  # syntax is another validator's job
        problems = []
        for cls, methods in sorted(before.items()):
            now = after.get(cls)
            for name, sig in sorted(methods.items()):
                if now is None or name not in now:
                    problems.append(f"{cls}.{name}({', '.join(_names(sig))}) was removed")
                elif not _still_compatible(sig, now[name]):
                    problems.append(
                        f"{cls}.{name} changed its parameters from "
                        f"({', '.join(_names(sig))}) to ({', '.join(_names(now[name]))})")
        if problems:
            errors.append(
                f"{ERROR_PREFIX} in '{path}': this page object is already committed "
                f"and other stories' step definitions call its methods. Keep every "
                f"existing method with its parameters unchanged and only ADD new "
                f"ones. Restore: " + "; ".join(problems) + ".")
    return errors
