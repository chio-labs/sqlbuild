"""CLI argument parsing through the native argv parser, with post-parse normalization."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.entry.models import (
    ParsedCliInvocation,
    SelectorFileSummary,
    SelectorInputs,
)


def read_selector_file_inputs(paths: list[str]) -> SelectorInputs:
    """Read newline-delimited selectors while retaining file provenance."""

    selectors: list[str] = []
    files: list[SelectorFileSummary] = []
    for raw_path in paths:
        path: Path = Path(raw_path)
        file_selector_count: int = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped: str = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            selectors.append(stripped)
            file_selector_count += 1
        files.append(SelectorFileSummary(path=path, selector_count=file_selector_count))
    return SelectorInputs(selectors=tuple(selectors), files=tuple(files))


def parse_cli_invocation(*, argv: Sequence[str] | None, use_color: bool) -> ParsedCliInvocation:
    """Parse CLI arguments into a namespace; help, version and errors print and exit."""

    args: CliNamespace = CliNamespace()
    raw_args: list[str] = list(sys.argv[1:] if argv is None else argv)
    rows: list[tuple[str, object]] | None
    exit_code: int | None
    rows, exit_code = _native.parse_cli_arguments(
        raw_args,
        list(vars(args).items()),
        use_color=use_color,
        columns=shutil.get_terminal_size().columns,
    )
    if rows is None:
        return ParsedCliInvocation(args=None, exit_code=exit_code)
    name: str
    value: object
    for name, value in rows:
        setattr(args, name, value)
    return ParsedCliInvocation(args=args, exit_code=None)
