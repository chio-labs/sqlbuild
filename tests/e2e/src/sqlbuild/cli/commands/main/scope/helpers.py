"""Scope E2E subprocess helpers."""

import subprocess
from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import REPO_ROOT


def run_scope_alias(
    *, alias: str, project_dir: Path, args: tuple[str, ...]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", alias, "--project-dir", str(project_dir), "scope", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
