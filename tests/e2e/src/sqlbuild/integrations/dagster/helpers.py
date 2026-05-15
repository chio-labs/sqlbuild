"""Helpers for Dagster integration e2e tests."""

from __future__ import annotations

from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import REPO_ROOT


def write_sqb_capture_command(
    *, root: Path, command_log_path: Path, selector_log_path: Path
) -> tuple[str, ...]:
    """Write a wrapper that records sqb args and select-file contents before exec."""

    sqb_executable: Path = REPO_ROOT / ".venv" / "bin" / "sqb"
    script_path: Path = root / "capture_sqb.py"
    script_path.write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "import os",
                "import sys",
                "from pathlib import Path",
                f"command_log_path = Path({str(command_log_path)!r})",
                f"selector_log_path = Path({str(selector_log_path)!r})",
                f"sqb_executable = {str(sqb_executable)!r}",
                "args = sys.argv[1:]",
                "command_log_path.write_text(' '.join(args), encoding='utf-8')",
                "if '--select-file' in args:",
                "    selector_path = Path(args[args.index('--select-file') + 1])",
                "    selector_contents = selector_path.read_text(encoding='utf-8')",
                "    selector_log_path.write_text(selector_contents, encoding='utf-8')",
                "os.execv(sqb_executable, (sqb_executable, *args))",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return ("python", str(script_path))
