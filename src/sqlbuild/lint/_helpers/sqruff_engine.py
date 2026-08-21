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

from sqlbuild.compiler.compile.main.map_expanded_offset import map_expanded_offset
from sqlbuild.compiler.compile.models import MappedOffset
from sqlbuild.lint._helpers.sqlbuild_tokens import (
    interpolation_text_at,
    neutralize_interpolation,
    restore_interpolation,
)
from sqlbuild.lint._helpers.sqruff_scaffold import read_configured_dialect
from sqlbuild.lint.constants import (
    GENERATED_SQL_MESSAGE_SUFFIX,
    GENERATED_SQL_MESSAGE_TEMPLATE,
    LINT_ENGINE_SQRUFF,
    SQRUFF_CHARACTER_KEY,
    SQRUFF_DIALECTS_COMMAND,
    SQRUFF_EXPECTED_EXIT_CODES,
    SQRUFF_LINE_KEY,
    SQRUFF_MINIMUM_POSITION,
    SQRUFF_RANGE_KEY,
    SQRUFF_START_KEY,
    VIOLATION_SEVERITY_FAULT,
    VIOLATION_SEVERITY_WARNING,
)
from sqlbuild.lint.exceptions import SqruffOutputError, UnsupportedDialectError
from sqlbuild.lint.models import InterpolationSite, LintBody, LintConfig, LintViolation

_SQRUFF_ERROR_SEVERITY: str = "Error"
_TEMP_BODY_PREFIX: str = "body_"


class _SqruffRun:
    """One temp-directory sqruff invocation over extracted SQL bodies."""

    def __init__(self) -> None:
        self.temp_to_original: dict[str, tuple[Path, int, int]] = {}
        self.temp_sites: dict[str, tuple[InterpolationSite, ...]] = {}
        self.neutralized_bodies: dict[str, str] = {}
        self.fixed_bodies: dict[str, str] = {}

    def write_bodies(
        self, *, bodies: Mapping[Path, tuple[str, tuple[tuple[int, int], ...]]], temp_path: Path
    ) -> list[str]:
        """Write each interpolation-neutralized body to a temp file."""
        command_paths: list[str] = []
        index: int = 0
        for original_path in sorted(bodies):
            contents: str
            ranges: tuple[tuple[int, int], ...]
            contents, ranges = bodies[original_path]
            body_start: int
            body_end: int
            for body_start, body_end in ranges:
                neutralized: str
                sites: tuple[InterpolationSite, ...]
                neutralized, sites = neutralize_interpolation(body=contents[body_start:body_end])
                temp_file: Path = temp_path / f"{_TEMP_BODY_PREFIX}{index}.sql"
                index += 1
                _ = temp_file.write_text(neutralized, encoding="utf-8")
                self.temp_to_original[temp_file.name] = (original_path, body_start, body_end)
                self.temp_sites[temp_file.name] = sites
                self.neutralized_bodies[temp_file.name] = neutralized
                command_paths.append(str(temp_file))
        return command_paths

    def reload_fixed_bodies(self, *, temp_path: Path) -> None:
        """Read back fixed temps and restore their interpolation tokens."""
        temp_file_name: str
        for temp_file_name in self.temp_to_original:
            reloaded: str = (temp_path / temp_file_name).read_text(encoding="utf-8")
            self.fixed_bodies[temp_file_name] = restore_interpolation(
                fixed=reloaded, sites=self.temp_sites[temp_file_name]
            )

    def spliced_contents(
        self, *, bodies: Mapping[Path, tuple[str, tuple[tuple[int, int], ...]]]
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
    bodies: tuple[LintBody, ...],
    contents_by_path: Mapping[Path, str],
    config: LintConfig,
    project_dir: Path,
) -> dict[Path, tuple[LintViolation, ...]]:
    """Lint expanded SQL bodies and map diagnostics back to authored positions."""

    if not bodies:
        return {}
    temp_to_body: dict[str, LintBody] = {}
    stdout: str
    with tempfile.TemporaryDirectory(prefix="sqlbuild-sqruff-") as temp_dir:
        temp_path: Path = Path(temp_dir)
        command_paths: list[str] = []
        index: int = 0
        body: LintBody
        for body in bodies:
            temp_file: Path = temp_path / f"{_TEMP_BODY_PREFIX}{index}.sql"
            index += 1
            _ = temp_file.write_text(body.lint_text, encoding="utf-8")
            temp_to_body[temp_file.name] = body
            command_paths.append(str(temp_file))
        _stdout_exit_code, stdout = _invoke_run_cli(
            arguments=_lint_arguments(
                command_paths=command_paths, config=config, project_dir=project_dir
            )
        )
        _assert_expected_exit_code(exit_code=_stdout_exit_code)
    violations_by_file: dict[Path, list[LintViolation]] = _lint_violations(
        diagnostics=_parse_diagnostics(stdout=stdout),
        temp_to_body=temp_to_body,
        contents_by_path=contents_by_path,
    )
    return {body.file_path: tuple(violations_by_file.get(body.file_path, ())) for body in bodies}


def _lint_arguments(
    *, command_paths: list[str], config: LintConfig, project_dir: Path
) -> list[str]:
    arguments: list[str] = ["lint", "--format", "json"]
    config_file: Path = project_dir / config.sqruff_config_path
    if config_file.is_file():
        _assert_dialect_supported(config_file=config_file)
        arguments.extend(["--config", str(config_file)])
    arguments.extend(command_paths)
    return arguments


def _lint_violations(
    *,
    diagnostics: dict[str, list[dict[str, object]]],
    temp_to_body: dict[str, LintBody],
    contents_by_path: Mapping[Path, str],
) -> dict[Path, list[LintViolation]]:
    violations_by_file: dict[Path, list[LintViolation]] = {}
    reported_path: str
    entries: list[dict[str, object]]
    for reported_path, entries in diagnostics.items():
        body: LintBody | None = temp_to_body.get(Path(reported_path).name)
        if body is None:
            raise SqruffOutputError(
                f"sqruff reported diagnostics for unknown path '{reported_path}'"
            )
        violation: dict[str, object]
        for violation in entries:
            violations_by_file.setdefault(body.file_path, []).append(
                _authored_violation(
                    violation=violation,
                    body=body,
                    contents=contents_by_path[body.file_path],
                )
            )
    return violations_by_file


def _authored_violation(
    *, violation: dict[str, object], body: LintBody, contents: str
) -> LintViolation:
    local_line: int
    local_character: int
    local_line, local_character = _diagnostic_start(violation=violation)
    lint_starts: tuple[int, ...] = _line_starts(body.lint_text)
    clamped_line: int = min(local_line, len(lint_starts) - 1)
    lint_offset: int = lint_starts[clamped_line] + local_character
    mapped: MappedOffset = map_expanded_offset(offset=lint_offset, passes=body.passes)
    absolute_offset: int = body.body_start + mapped.offset
    starts: tuple[int, ...] = _line_starts(contents)
    line_index: int = bisect_right(starts, absolute_offset) - 1
    code: object = violation.get("code")
    severity: object = violation.get("severity")
    is_fault: bool = severity == _SQRUFF_ERROR_SEVERITY
    return LintViolation(
        file_path=body.file_path,
        line=line_index + 1,
        column=absolute_offset - starts[line_index] + 1,
        code=str(code) if code is not None else "sqruff",
        message=_violation_message(
            violation=violation, mapped=mapped, contents=contents, absolute_offset=absolute_offset
        ),
        severity=VIOLATION_SEVERITY_FAULT if is_fault else VIOLATION_SEVERITY_WARNING,
        engine=LINT_ENGINE_SQRUFF,
    )


def _violation_message(
    *, violation: dict[str, object], mapped: MappedOffset, contents: str, absolute_offset: int
) -> str:
    raw_message: object = violation.get("message")
    message: str = str(raw_message) if raw_message is not None else ""
    if not mapped.generated:
        return message
    token: str | None = interpolation_text_at(body=contents, start=absolute_offset)
    if token is None:
        return f"{message} {GENERATED_SQL_MESSAGE_SUFFIX}"
    return f"{message} {GENERATED_SQL_MESSAGE_TEMPLATE.format(token=token)}"


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
            _assert_dialect_supported(config_file=config_file)
            arguments.extend(["--config", str(config_file)])
        arguments.extend(command_paths)
        outcome: tuple[int, str] = _invoke_run_cli(arguments=arguments)
        _assert_expected_exit_code(exit_code=outcome[0])
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


def _assert_expected_exit_code(*, exit_code: int) -> None:
    if exit_code in SQRUFF_EXPECTED_EXIT_CODES:
        return
    raise SqruffOutputError(
        f"sqruff exited with unexpected code {exit_code}; expected one of "
        f"{sorted(SQRUFF_EXPECTED_EXIT_CODES)}"
    )


def _assert_dialect_supported(*, config_file: Path) -> None:
    configured: str | None = read_configured_dialect(config_file=config_file)
    if configured is None:
        return
    supported: frozenset[str] = _supported_dialects()
    if configured in supported:
        return
    raise UnsupportedDialectError(
        f"{config_file} declares dialect '{configured}', which sqruff does not support; "
        f"sqruff would silently lint with its default dialect. Supported dialects: "
        f"{', '.join(sorted(supported))}"
    )


def _supported_dialects() -> frozenset[str]:
    _exit_code, stdout = _invoke_run_cli(arguments=[SQRUFF_DIALECTS_COMMAND])
    dialects: frozenset[str] = frozenset(
        line.strip() for line in stdout.splitlines() if line.strip()
    )
    if not dialects:
        raise SqruffOutputError(
            f"sqruff '{SQRUFF_DIALECTS_COMMAND}' returned no dialects; cannot validate "
            f"the configured dialect"
        )
    return dialects


def _diagnostic_start(*, violation: dict[str, object]) -> tuple[int, int]:
    range_info: object = violation.get(SQRUFF_RANGE_KEY)
    if not isinstance(range_info, dict):
        raise SqruffOutputError(
            f"sqruff diagnostic is missing a '{SQRUFF_RANGE_KEY}' object: {violation!r}"
        )
    range_mapping: dict[object, object] = cast(dict[object, object], range_info)
    start_info: object = range_mapping.get(SQRUFF_START_KEY)
    if not isinstance(start_info, dict):
        raise SqruffOutputError(
            f"sqruff diagnostic range is missing a '{SQRUFF_START_KEY}' object: {violation!r}"
        )
    start_mapping: dict[object, object] = cast(dict[object, object], start_info)
    raw_line: object = start_mapping.get(SQRUFF_LINE_KEY)
    raw_character: object = start_mapping.get(SQRUFF_CHARACTER_KEY)
    if not isinstance(raw_line, int) or not isinstance(raw_character, int):
        raise SqruffOutputError(
            f"sqruff diagnostic start must carry integer '{SQRUFF_LINE_KEY}' and "
            f"'{SQRUFF_CHARACTER_KEY}': {violation!r}"
        )
    if raw_line < SQRUFF_MINIMUM_POSITION or raw_character < SQRUFF_MINIMUM_POSITION:
        raise SqruffOutputError(
            f"sqruff diagnostic positions are one-based, got line {raw_line} character "
            f"{raw_character}: {violation!r}"
        )
    return raw_line - SQRUFF_MINIMUM_POSITION, raw_character - SQRUFF_MINIMUM_POSITION


def _parse_diagnostics(*, stdout: str) -> dict[str, list[dict[str, object]]]:
    stripped: str = stdout.strip()
    if not stripped:
        return {}
    try:
        parsed: object = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise SqruffOutputError(
            f"sqruff did not emit JSON diagnostics: {error}; output was {stripped[:200]!r}"
        ) from error
    if not isinstance(parsed, dict):
        raise SqruffOutputError(
            f"sqruff JSON diagnostics must be an object keyed by path, got {type(parsed).__name__}"
        )
    diagnostics: dict[str, list[dict[str, object]]] = {}
    path: object
    entries: object
    for path, entries in parsed.items():
        if not isinstance(entries, list):
            raise SqruffOutputError(
                f"sqruff diagnostics for '{path}' must be a list, got {type(entries).__name__}"
            )
        diagnostics[str(path)] = [entry for entry in entries if isinstance(entry, dict)]
    return diagnostics


def _line_starts(contents: str) -> tuple[int, ...]:
    starts: list[int] = [0]
    index: int = contents.find("\n")
    while index >= 0:
        starts.append(index + 1)
        index = contents.find("\n", index + 1)
    return tuple(starts)
