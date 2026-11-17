"""Code safety: generated test code drives the application, and nothing else (S1).

WHY
    A story's text is untrusted input, and Agent 2 turns it into Python that
    Agent 4 RUNS on the pull request - before a person has reviewed it - with
    the application's login in the environment (APP_PASSWORD, APP_USER_<ROLE>)
    and a token on the runner. The import validator allowed every standard
    library module and every package in requirements.txt, so code reading the
    environment, starting a process or opening a connection passed every gate:
    a story worded to ask for it ("log the credentials to our audit service")
    would have been coded and run.

WHAT
    Generated test code reaches the application only through the page objects'
    BasePage helpers and the fixtures; it never needs the process, the network,
    the file system or the environment. So, in every generated Python file:

      modules   no import of a module that starts processes, opens connections,
                loads or runs code, or touches the file system wholesale
                (DENY_MODULES - by dotted prefix, so `urllib.parse` stays allowed
                and `urllib.request` does not);
      os        no environment, process or file-changing call through `os`
                (DENY_OS) - `os.path` stays allowed;
      builtins  no eval / exec / compile / __import__ / open / globals / vars
                / breakpoint / input, and no getattr / setattr / delattr with a
                name that is not a literal (a computed name can reach anything);
      dunders   no `__builtins__`, `__globals__`, `__subclasses__`, `__code__`
                and the like - the classic ways out of a restriction;
      browser   no Playwright escape hatch: running JavaScript (`evaluate`,
                `add_init_script` ...), intercepting or sending requests
                (`route`, `.request`, `set_extra_http_headers`), reading or
                writing the session (`cookies`, `storage_state`), or `goto`
                outside BasePage.navigate - JavaScript and requests reach any
                host, and the session is the signed-in user;
      files     no `read_text` / `write_text` / `read_bytes` / `write_bytes`,
                `.open()` on a path (`Path(...).open()`, or a name a path was
                assigned to - a page object's own `open()` is not a path), no
                `save_as`, no `os.remove`-style call, and no module that reads
                or writes files by itself (`io`, `codecs`, `zipfile` ...);
      detours   no way round the above: a denied module reached as another
                module's attribute (`os.path.os`, `logging.sys`), a denied name
                fetched by `getattr(x, "environ")`, a star import from `os`,
                interpreter frames (`f_globals`, `tb_frame` ...) or
                `operator.attrgetter` / `methodcaller`.

    Two doors stay open on purpose, and BasePage guards them at run time:
    `navigate()` goes only to the application's own host (or one listed in
    `browser.navigation_hosts`), so a URL cannot carry a value to another
    host; `upload_file()` attaches only files inside the project, outside
    hidden paths (`.git`, `.env`), so the runner's files cannot be sent.

    Static analysis (ast) only: nothing is executed. Each finding is an error
    in the shape the repair loop reads (`Unsafe code error in '<path>': ...`),
    so the model is asked once more to remove it, and the final gate refuses a
    story that still has one. Agent 4 runs the same check on a pull request's
    changed test code before its browser run (scripts/check_code_safety.py),
    so code that reaches a branch any other way never runs with the login.

    A project that needs one of these in its OWN generated code (a test that
    must upload a file it writes, say) allows it by name:
    `agents.agent2_coder.code_safety.allow` in config.yaml - a reviewed
    decision, visible in the config, never the model's.

Generic: nothing here names an application, a page or a test.
"""
from __future__ import annotations

import ast
from typing import Iterable

# Dotted module prefixes no generated test module may import.
DENY_MODULES = (
    # processes and the operating system
    "subprocess", "multiprocessing", "concurrent.futures.process", "pty", "pexpect",
    "signal", "resource", "shutil", "tempfile", "glob", "fcntl", "posix", "nt",
    # the network
    "socket", "socketserver", "ssl", "select", "selectors", "asyncio", "http",
    "urllib.request", "urllib.error", "urllib3", "ftplib", "smtplib", "poplib",
    "imaplib", "telnetlib", "nntplib", "xmlrpc", "requests", "httpx", "aiohttp",
    "websocket", "websockets", "paramiko", "pycurl", "grpc", "boto3", "botocore",
    "dns", "webbrowser",
    # loading or running code, and serialised objects
    "importlib", "runpy", "code", "codeop", "builtins", "ctypes", "cffi", "pickle",
    "marshal", "shelve", "dill", "cloudpickle", "sys", "inspect", "gc",
    # reading or writing files by themselves
    "io", "codecs", "fileinput", "zipfile", "tarfile", "gzip", "bz2", "lzma",
    "sqlite3", "mmap", "linecache", "netrc", "configparser", "dotenv",
)

# `os.<name>` calls and reads that leave the test: the environment, processes,
# and changes to the file system. `os.path` is not among them.
DENY_OS = frozenset({
    "environ", "environb", "getenv", "getenvb", "putenv", "unsetenv", "system", "popen",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "fork", "forkpty", "kill", "killpg", "posix_spawn", "posix_spawnp", "startfile",
    "remove", "unlink", "rmdir", "removedirs", "rename", "renames", "replace", "chmod",
    "chown", "symlink", "link", "truncate", "open", "fdopen", "write", "listdir",
    "scandir", "walk",
})

DENY_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "open", "globals", "vars", "breakpoint",
    "input", "memoryview",
})
# getattr(obj, "literal") is fine; a computed name can reach anything.
_DYNAMIC_ATTR = frozenset({"getattr", "setattr", "delattr", "hasattr"})

DENY_DUNDERS = frozenset({
    "__builtins__", "__globals__", "__subclasses__", "__code__", "__closure__",
    "__func__", "__self__", "__dict__", "__mro__", "__bases__", "__base__",
    "__loader__", "__spec__", "__getattribute__", "__reduce__", "__reduce_ex__",
    "__import__", "__class__",
})

# Attribute names that reach past the page objects: JavaScript, requests, the
# session, and navigation that is not BasePage.navigate().
DENY_ATTRS = frozenset({
    "evaluate", "evaluate_all", "evaluate_handle", "eval_on_selector",
    "eval_on_selector_all", "add_init_script", "add_script_tag", "add_style_tag",
    "expose_function", "expose_binding", "route", "route_from_har", "unroute",
    "unroute_all", "request", "set_extra_http_headers", "set_http_credentials",
    "cookies", "add_cookies", "clear_cookies", "storage_state", "new_context",
    "new_page", "goto", "set_content", "wait_for_function", "dispatch_event",
    "read_text", "write_text", "read_bytes", "write_bytes", "save_as",
    # interpreter frames and code objects: a way back to globals and builtins
    "f_globals", "f_locals", "f_builtins", "f_back", "f_code", "tb_frame",
    "gi_frame", "cr_frame", "ag_frame", "co_code",
    # a call by a computed name
    "attrgetter", "methodcaller",
})

# `os.<name>` with a name no other object has: refused on ANY base, so
# `os.path.os.environ` or a re-bound module does not slip through.
DENY_OS_ANYWHERE = frozenset({
    "environ", "environb", "getenv", "getenvb", "putenv", "unsetenv", "popen", "fork",
    "forkpty", "killpg", "posix_spawn", "posix_spawnp", "startfile",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
})

# Modules other modules carry as an attribute (`os.path.os`, `logging.sys`):
# reaching one that way is reaching it.
DENY_MODULE_ATTRS = frozenset({
    "os", "sys", "subprocess", "socket", "builtins", "importlib", "shutil", "ctypes",
    "pickle", "marshal", "posix", "nt", "requests", "urllib3", "httpx", "runpy",
    "multiprocessing", "pty",
})

_WHY = ("generated test code reaches the application only through the page objects' "
        "BasePage helpers and the fixtures - never the environment, a process, the "
        "network, the file system, or the browser past those helpers (it runs before a "
        "person reviews it, with the application's login available)")


def _denied_attr_name(name: str, allow: set) -> bool:
    """A name `getattr(x, "<name>")` may not fetch: every denied attribute,
    dunder, os call or module - by literal name is still by name."""
    return name not in allow and (name in DENY_ATTRS or name in DENY_DUNDERS
                                  or name in DENY_OS_ANYWHERE or name == "system"
                                  or name in DENY_MODULE_ATTRS or name in DENY_BUILTINS)


def _denied_module(name: str, allow: set) -> str | None:
    for prefix in DENY_MODULES:
        if (name == prefix or name.startswith(prefix + ".")) and prefix not in allow \
                and name not in allow:
            return prefix
    return None


class _Finder(ast.NodeVisitor):
    def __init__(self, allow: set):
        self.allow = allow
        self.found: list = []          # (line, what)
        self.os_names: set = {"os"}    # names bound to the os module
        self.path_names: set = set()   # names bound to pathlib / its classes
        self.path_vars: set = set()    # names a path was assigned to

    def _pathish(self, expr) -> bool:
        """`expr` builds or holds a filesystem path: it mentions pathlib, or a
        name or attribute (`self.data_file`) a path was assigned to."""
        names = self.path_names | self.path_vars
        for n in ast.walk(expr):
            if isinstance(n, ast.Name) and n.id in names:
                return True
            if isinstance(n, ast.Attribute) and ast.unparse(n) in self.path_vars:
                return True
        return False

    def _bind(self, target, value) -> None:
        if value is None or not self._pathish(value):
            return
        if isinstance(target, ast.Name):
            self.path_vars.add(target.id)
        elif isinstance(target, ast.Attribute):
            self.path_vars.add(ast.unparse(target))      # `self.data_file`
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind(elt, value)
        elif isinstance(target, ast.Starred):
            self._bind(target.value, value)

    def visit_Assign(self, node):
        for t in node.targets:
            self._bind(t, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self._bind(node.target, node.value)
        if self._pathish(node.annotation):
            self._bind(node.target, node.annotation)
        self.generic_visit(node)

    def visit_NamedExpr(self, node):
        self._bind(node.target, node.value)
        self.generic_visit(node)

    def visit_With(self, node):
        for item in node.items:
            if item.optional_vars is not None:
                self._bind(item.optional_vars, item.context_expr)
        self.generic_visit(node)

    def visit_For(self, node):
        self._bind(node.target, node.iter)
        self.generic_visit(node)

    def visit_arg(self, node):
        if node.annotation is not None and self._pathish(node.annotation):
            self.path_vars.add(node.arg)
        self.generic_visit(node)

    def _add(self, node, what: str) -> None:
        self.found.append((getattr(node, "lineno", 0), what))

    def visit_Import(self, node):
        for alias in node.names:
            hit = _denied_module(alias.name, self.allow)
            if hit:
                self._add(node, f"imports `{alias.name}`")
            if alias.name == "os":
                self.os_names.add(alias.asname or "os")
            elif alias.name.startswith("os.") and not alias.asname:
                self.os_names.add("os")         # `import os.path` binds `os`
            if alias.name == "pathlib":
                self.path_names.add(alias.asname or "pathlib")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        hit = _denied_module(module, self.allow) if not node.level else None
        if hit:
            self._add(node, f"imports from `{module}`")
        if module == "pathlib" and not node.level:
            for alias in node.names:
                self.path_names.add(alias.asname or alias.name)
        if module == "os" and not node.level and not hit:
            for alias in node.names:
                if alias.name == "*":
                    self._add(node, "imports `*` from `os`")
                elif alias.name in DENY_OS and alias.name not in self.allow:
                    self._add(node, f"imports `os.{alias.name}`")
        for alias in node.names:
            if not hit and not node.level and module != "os" and alias.name not in self.allow and (
                    alias.name in DENY_ATTRS or alias.name in DENY_OS_ANYWHERE):
                self._add(node, f"imports `{alias.name}` from `{module}`")
            full = f"{module}.{alias.name}" if module else alias.name
            if not hit and not node.level and _denied_module(full, self.allow) \
                    and _denied_module(full, self.allow) != _denied_module(module, self.allow):
                self._add(node, f"imports `{full}`")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr in self.allow:
            pass
        elif isinstance(node.value, ast.Name) and node.value.id in self.os_names \
                and node.attr in DENY_OS:
            self._add(node, f"uses `os.{node.attr}`")
        elif node.attr in DENY_OS_ANYWHERE:
            self._add(node, f"uses `.{node.attr}`")
        elif node.attr in DENY_MODULE_ATTRS:
            self._add(node, f"reaches the `{node.attr}` module through an attribute")
        elif node.attr == "open" and self._pathish(node.value):
            self._add(node, "opens a file through a path")
        elif node.attr in DENY_DUNDERS and node.attr not in self.allow:
            self._add(node, f"reaches `{node.attr}`")
        elif node.attr in DENY_ATTRS and node.attr not in self.allow:
            self._add(node, f"uses `.{node.attr}`")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in DENY_DUNDERS and node.id not in self.allow:
            self._add(node, f"reaches `{node.id}`")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            name = node.func.id
            if name in DENY_BUILTINS and name not in self.allow:
                self._add(node, f"calls `{name}()`")
            elif name in _DYNAMIC_ATTR and name not in self.allow:
                literal = (len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                           and isinstance(node.args[1].value, str))
                if not literal:
                    self._add(node, f"calls `{name}()` with a name that is not a literal")
                elif _denied_attr_name(node.args[1].value, self.allow):
                    self._add(node, f"calls `{name}()` for `{node.args[1].value}`")
        self.generic_visit(node)


def unsafe_calls(source: str, allow=()) -> list:
    """[(line, what)] for each unsafe use in one Python source. A file that
    does not parse yields nothing here - the other validators report it."""
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return []
    finder = _Finder(set(allow or ()))
    finder.visit(tree)
    return sorted(set(finder.found))


# Where generated Python may live: the page objects and the step definitions.
CODE_DIRS = ("pages/", "tests/step_defs/")


def code_path_problem(path: str, code_dirs=CODE_DIRS) -> str:
    """'' when generated code may be written at `path`, else why not. Python
    only under the test-code directories, and never a `conftest.py` or an
    `__init__.py` there: those run for every test and belong to the framework.
    A file that is not Python (a feature file) is not code."""
    p = _norm(path)
    if not p.endswith(".py"):
        return ""
    name = p.rsplit("/", 1)[-1]
    if name in ("conftest.py", "__init__.py"):
        return (f"`{p}` runs for every test and belongs to the framework - generated code "
                "goes in page objects and step definitions only")
    dirs = tuple(d if d.endswith("/") else d + "/" for d in code_dirs)
    if not p.startswith(dirs):
        return (f"`{p}` is outside {', '.join(f'`{d}`' for d in dirs)} - generated Python "
                "lives only in page objects and step definitions")
    return ""


def settings(raw: dict | None = None) -> dict:
    """`agents.agent2_coder.code_safety` over the defaults: {"enabled",
    "allow", "code_dirs"}."""
    out = {"enabled": True, "allow": [], "code_dirs": list(CODE_DIRS)}
    if raw is None:
        try:
            import yaml
            from config.paths import CONFIG_YAML
            data = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
            raw = (((data.get("agents") or {}).get("agent2_coder") or {})
                   .get("code_safety") or {})
        except Exception:                                          # noqa: BLE001
            raw = {}
    if isinstance(raw, dict):
        if isinstance(raw.get("enabled"), bool):
            out["enabled"] = raw["enabled"]
        if isinstance(raw.get("allow"), list):
            out["allow"] = [str(a) for a in raw["allow"]]
        if isinstance(raw.get("code_dirs"), list) and raw["code_dirs"]:
            out["code_dirs"] = [str(d) for d in raw["code_dirs"]]
    return out


def trusted_paths(config: dict | None = None) -> set:
    """The framework's own files among the test code: `app_under_test.
    reserved_paths` (the base page, the reference files). They read the
    environment and drive the browser directly on purpose, are never
    generated (the path policy refuses them), and change only in reviewed
    framework pull requests - so neither check reads them. Every
    `conftest.py` is the framework's too (`is_framework_file`)."""
    if config is None:
        try:
            import yaml
            from config.paths import CONFIG_YAML
            config = yaml.safe_load(CONFIG_YAML.read_text(encoding="utf-8")) or {}
        except Exception:                                          # noqa: BLE001
            config = {}
    reserved = ((config or {}).get("app_under_test") or {}).get("reserved_paths") or []
    return {_norm(p) for p in reserved}


def _norm(path) -> str:
    p = str(path or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def is_framework_file(path, trusted: set) -> bool:
    p = _norm(path)
    return p in trusted or p.rsplit("/", 1)[-1] == "conftest.py"


def validate_code_safety(generated_files: Iterable, allow=None, enabled=None,
                         trusted: set | None = None) -> list:
    """Errors for unsafe code in generated .py files, in the repair loop's
    shape. [] when everything is safe, or when switched off in config. The
    framework's own files (`trusted_paths`, any conftest.py) are not read:
    a batch can carry one only as context, never as generated code."""
    s = settings() if (allow is None or enabled is None) else {}
    allow = s.get("allow", []) if allow is None else allow
    enabled = s.get("enabled", True) if enabled is None else enabled
    if not enabled:
        return []
    trusted = trusted_paths() if trusted is None else trusted
    errors = []
    for gf in generated_files or []:
        path = getattr(gf, "file_path", "") or ""
        if not path.endswith(".py") or is_framework_file(path, trusted):
            continue
        for line, what in unsafe_calls(getattr(gf, "content", "") or "", allow):
            errors.append(f"Unsafe code error in '{path}': line {line} {what}. Remove it: "
                          f"{_WHY}. If the step needs something the page objects do not "
                          "offer, use or add a page-object method built on BasePage "
                          "helpers.")
    return errors
