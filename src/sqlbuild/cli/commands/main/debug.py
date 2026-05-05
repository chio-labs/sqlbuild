"""CLI debug command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.debug.checks import build_debug_result
from sqlbuild.cli.commands.main.helpers.debug.models import DebugResult
from sqlbuild.cli.commands.main.helpers.debug.output import format_debug_json, format_debug_text
from sqlbuild.shared.helpers.colors import supports_color


def run_debug(
    project_dir: Path | None,
    no_color: bool = False,
    no_connection: bool = False,
    json_output: bool = False,
) -> int:
    """Validate project config and the active connection."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    result: DebugResult = build_debug_result(
        project_dir=effective_project_dir,
        check_connection=not no_connection,
    )
    if json_output:
        sys.stdout.write(format_debug_json(result) + "\n")
    else:
        sys.stdout.write(format_debug_text(result, use_color=(not no_color) and supports_color()))
    sys.stdout.flush()
    return 0 if result.success else 1
