"""Fresh-interpreter compile runs for compile reuse import checks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from sqlbuild.cli.compile_reuse.constants import REUSE_DISABLE_ENV_VAR


def compile_in_fresh_process(
    *, project_dir: Path, checked_modules: tuple[str, ...]
) -> tuple[int, tuple[str, ...], str]:
    """Compile once with reuse enabled and report which checked modules were imported."""

    script: str = (
        "import contextlib, io, json, sys\n"
        "from sqlbuild.cli.entry.main.entry import main\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        f"    code = main(['--project-dir', {str(project_dir)!r}, 'compile', '--json'])\n"
        f"names = {checked_modules!r}\n"
        "print(json.dumps({'code': code, "
        "'loaded': [name for name in names if name in sys.modules]}))\n"
    )
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, REUSE_DISABLE_ENV_VAR: "0"},
    )
    outcome: dict[str, object] = json.loads(result.stdout.strip().splitlines()[-1])
    return (
        cast(int, outcome["code"]),
        tuple(cast(list[str], outcome["loaded"])),
        result.stderr,
    )
