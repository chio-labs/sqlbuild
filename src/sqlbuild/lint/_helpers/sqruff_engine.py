"""In-process sqruff engine wrapper with fd-level stdout capture."""

from __future__ import annotations

import json
import os
import tempfile
from bisect import bisect_right
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from sqruff import run_cli

from sqlbuild.lint.constants import (
    LINT_ENGINE_SQRUFF,
    VIOLATION_SEVERITY_FAULT,
    VIOLATION_SEVERITY_WARNING,
)
from sqlbuild.lint.models import LintConfig, LintViolation

_SQRUFF_ERROR_SEVERITY: str = "Error"
_TEMP_BODY_PREFIX: str = "body_"


class _SqruffRun:
    """One temp-directory sqruff invocation over extracted SQL bodies."""

    def __init__(self) -> None:
        self.temp_to_original: dict[str, tuple[Path, int, int]] = {}
        self.fixed_bodies: dict[str, str] = {}

    def write_bodies(
        self, *, bodies: Mapping[Path, tuple[str, tuple[tuple[int, int], ...]]], temp_path: Path
    ) -> list[str]:
        """Write each body to a temp file and return the command paths."""
        command_paths: list[str] = []
        index: int = 0
        for original_path in sorted(bodies):
            contents: str
            ranges: tuple[tuple[int, int], ...]
            contents, ranges = bodies[original_path]
            body_start: int
            body_end: int
            for body_start, body_end in ranges:
                temp_file: Path = temp_path / f"{_TEMP_BODY_PREFIX}{index}.sql"
                index += 1
                temp_file.write_text(contents[body_start:body_end], encoding="utf-8")
                self.temp_to_original[temp_file.name] = (original_path, body_start, body_end)
                command_paths.append(str(temp_file))
        return command_paths

    def reload_fixed_bodies(self, temp_path: Path) -> None:
        """Read back each temp file after sqruff rewrote it in place."""
        temp_file_name: str
        for temp_file_name in self.temp_to_original:
            self.fixed_bodies[temp_file_name] = (temp_path / temp_file_name).read_text(
                encoding="utf-8"
            )

    def violations(
        self,
        *,
        bodies: Mapping[Path, tuple[str, tuple[tuple[int, int], ...]]],
        diagnostics: dict[str, list[dict[str, object]]],
    ) -> dict[Path, list[LintViolation]]:
        """Map sqruff diagnostics from temp files back onto original files."""
        violations_by_file: dict[Path, list[LintViolation]] = {}
        reported_path: str
        entries: list[dict[str, object]]
        for reported_path, entries in diagnostics.items():
            mapped: tuple[Path, int, int] | None = self.temp_to_original.get(
                Path(reported_path).name
            )
            if mapped is None:
                continue
            line_starts: tuple[int, ...] = _line_starts(bodies[mapped[0]][0])
            violation: dict[str, object]
            for violation in entries:
                mapped_violation: LintViolation = _map_violation(
                    violation=violation,
                    file_path=mapped[0],
                    body_start=mapped[1],
                    line_starts=line_starts,
                )
                violations_by_file.setdefault(mapped[0], []).append(mapped_violation)
        return violations_by_file

    def spliced_contents(
        self, bodies: Mapping[Path, tuple[str, tuple[tuple[int, int], ...]]]
    ) -> dict[Path, str]:
        """Splice fixed temp bodies back into their original file contents."""
        replacements: dict[Path, list[tuple[int, int, str]]] = {}
        temp_file_name: str
        for temp_file_name, (original_path, body_start, body_end) in sorted(
            self.temp_to_original.items()
        ):
            replacements.setdefault(original_path, []).append(
                (body_start, body_end, self.fixed_bodies[temp_file_name])
            )
        spliced: dict[Path, str] = {}
        original_path: Path
        for original_path in bodies:
            updated: str = bodies[original_path][0]
            replacement_start: int
            replacement_end: int
            replacement_text: str
            for replacement_start, replacement_end, replacement_text in reversed(
                replacements.get(original_path, ())
            ):
                updated = updated[:replacement_start] + replacement_text + updated[replacement_end:]
            spliced[original_path] = updated
        return spliced


def run_sqruff_lint(
    *,
    bodies: Mapping[Path, tuple[str, tuple[tuple[int, int], ...]]],
    config: LintConfig,
    project_dir: Path,
) -> dict[Path, tuple[LintViolation, ...]]:
    """Run sqruff lint over extracted SQL bodies and map diagnostics back to files."""

    if not bodies:
        return {}
    sqruff_run: _SqruffRun = _SqruffRun()
    exit_code, stdout = _invoke_sqruff(
        bodies=bodies, config=config, project_dir=project_dir, fix=False, sqruff_run=sqruff_run
    )
    _ = exit_code
    violations_by_file: dict[Path, list[LintViolation]] = sqruff_run.violations(
        bodies=bodies, diagnostics=_parse_diagnostics(stdout=stdout)
    )
    return {file_path: tuple(violations_by_file.get(file_path, ())) for file_path in bodies}


def run_sqruff_fix(
    *,
    bodies: Mapping[Path, tuple[str, tuple[tuple[int, int], ...]]],
    config: LintConfig,
    project_dir: Path,
) -> dict[Path, str]:
    """Run sqruff fix over extracted SQL bodies and splice fixed text back in place."""

    if not bodies:
        return {}
    sqruff_run: _SqruffRun = _SqruffRun()
    exit_code, _stdout = _invoke_sqruff(
        bodies=bodies, config=config, project_dir=project_dir, fix=True, sqruff_run=sqruff_run
    )
    _ = exit_code
    return sqruff_run.spliced_contents(bodies=bodies)


def _invoke_sqruff(
    *,
    bodies: Mapping[Path, tuple[str, tuple[tuple[int, int], ...]]],
    config: LintConfig,
    project_dir: Path,
    fix: bool,
    sqruff_run: _SqruffRun,
) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="sqlbuild-sqruff-") as temp_dir:
        temp_path: Path = Path(temp_dir)
        command_paths: list[str] = sqruff_run.write_bodies(bodies=bodies, temp_path=temp_path)
        arguments: list[str] = ["fix" if fix else "lint", "--format", "json"]
        config_file: Path = project_dir / config.sqruff_config_path
        if config_file.is_file():
            arguments.extend(["--config", str(config_file)])
        arguments.extend(command_paths)
        outcome: tuple[int, str] = _invoke_run_cli(arguments=arguments)
        if fix:
            sqruff_run.reload_fixed_bodies(temp_path=temp_path)
        return outcome


def _invoke_run_cli(*, arguments: list[str]) -> tuple[int, str]:
    saved_stdout: int = os.dup(1)
    read_fd: int
    write_fd: int
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 1)
    try:
        exit_code: int = run_cli(arguments)
    finally:
        os.dup2(saved_stdout, 1)
        os.close(saved_stdout)
        os.close(write_fd)
        captured_bytes: bytes = b""
        while True:
            chunk: bytes = os.read(read_fd, 65536)
            if not chunk:
                break
            captured_bytes += chunk
        os.close(read_fd)
    return exit_code, captured_bytes.decode("utf-8", errors="replace")


def _parse_diagnostics(*, stdout: str) -> dict[str, list[dict[str, object]]]:
    stripped: str = stdout.strip()
    if not stripped:
        return {}
    try:
        parsed: object = json.loads(stripped)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    diagnostics: dict[str, list[dict[str, object]]] = {}
    path: object
    entries: object
    for path, entries in parsed.items():
        if isinstance(entries, list):
            diagnostics[str(path)] = [entry for entry in entries if isinstance(entry, dict)]
    return diagnostics


def _map_violation(
    *,
    violation: dict[str, object],
    file_path: Path,
    body_start: int,
    line_starts: tuple[int, ...],
) -> LintViolation:
    range_info: object = violation.get("range")
    line: int = 1
    column: int = 1
    if isinstance(range_info, dict):
        range_mapping: dict[object, object] = cast(dict[object, object], range_info)
        start_info: object = range_mapping.get("start")
        if isinstance(start_info, dict):
            start_mapping: dict[object, object] = cast(dict[object, object], start_info)
            raw_line: object = start_mapping.get("line")
            raw_character: object = start_mapping.get("character")
            local_line: int = raw_line if isinstance(raw_line, int) else 0
            local_character: int = raw_character if isinstance(raw_character, int) else 0
            clamped_line: int = min(local_line, len(line_starts) - 1)
            offset: int = body_start + line_starts[clamped_line] + local_character
            absolute_line_index: int = bisect_right(line_starts, offset) - 1
            line = absolute_line_index + 1
            column = offset - line_starts[absolute_line_index] + 1
    code: object = violation.get("code")
    message: object = violation.get("message")
    severity: object = violation.get("severity")
    is_fault: bool = severity == _SQRUFF_ERROR_SEVERITY
    return LintViolation(
        file_path=file_path,
        line=line,
        column=column,
        code=str(code) if code is not None else "sqruff",
        message=str(message) if message is not None else "",
        severity=VIOLATION_SEVERITY_FAULT if is_fault else VIOLATION_SEVERITY_WARNING,
        engine=LINT_ENGINE_SQRUFF,
    )


def _line_starts(contents: str) -> tuple[int, ...]:
    starts: list[int] = [0]
    index: int = contents.find("\n")
    while index >= 0:
        starts.append(index + 1)
        index = contents.find("\n", index + 1)
    return tuple(starts)
