"""Helpers for user-code loading tests."""

import os
import py_compile
import subprocess
import sys
from pathlib import Path

_PROJECT_FILES: dict[str, str] = {
    "rules/__init__.py": "",
    "rules/limits.py": "MAX_NAME_LENGTH: int = 40\n",
    "rules/naming.py": (
        "from rules.limits import MAX_NAME_LENGTH\n\nRULE_LIMIT: int = MAX_NAME_LENGTH * 1\n"
    ),
}
_LOAD_SCRIPT: str = (
    "import sys\n"
    "from importlib.util import module_from_spec\n"
    "from pathlib import Path\n"
    "from sqlbuild.runtime.user_code.main.user_code_spec import user_code_spec\n"
    "root = Path(sys.argv[1])\n"
    "sys.path.insert(0, str(root))\n"
    "spec = user_code_spec('rule_naming', root / 'rules' / 'naming.py', root=root)\n"
    "module = module_from_spec(spec)\n"
    "spec.loader.exec_module(module)\n"
    "print(module.RULE_LIMIT)\n"
)


def write_project_with_cached_bytecode(*, root: Path) -> None:
    """Write the project files and cache standard bytecode for each, as a previous run would."""

    for relative_path, contents in _PROJECT_FILES.items():
        path: Path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(contents, encoding="utf-8")
        _ = py_compile.compile(str(path), doraise=True)


def edit_keeping_size_and_mtime(*, root: Path, relative_path: str, old: str, new: str) -> None:
    """Apply a same-size edit and restore the file's previous timestamps."""

    path: Path = root / relative_path
    before: os.stat_result = path.stat()
    contents: str = path.read_text(encoding="utf-8")
    _ = path.write_text(contents.replace(old, new, 1), encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


def load_rule_limit(*, root: Path) -> str:
    """Load the rule module through the user-code loader in a fresh interpreter."""

    completed: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", _LOAD_SCRIPT, str(root)],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()
