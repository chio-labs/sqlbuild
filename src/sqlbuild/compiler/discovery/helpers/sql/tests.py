"""Parsing helpers for authored SQL-native test files."""

from __future__ import annotations

import re
from inspect import cleandoc
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.compile.constants import DEFAULT_SQL_TEST_MODE
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.discovery.exceptions import SqlTestParseError
from sqlbuild.compiler.discovery.helpers.sql.constants import (
    TEST_HEADER_ONLY_PATTERN,
    TEST_HEADER_PATTERN,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlTestBlock


def parse_sql_test_file(contents: str, file_path: Path) -> tuple[DiscoveredSqlTestBlock, ...]:
    """Parse one SQL-native test file into one or more raw TEST(...) blocks."""

    raw_test_blocks: tuple[str, ...] = _split_sql_test_blocks(
        file_path=file_path, contents=contents
    )
    if not raw_test_blocks:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )

    discovered_blocks: list[DiscoveredSqlTestBlock] = []
    test_index: int
    raw_test_block: str
    for test_index, raw_test_block in enumerate(raw_test_blocks, start=1):
        discovered_blocks.append(
            _parse_single_sql_test_block(
                file_path=file_path,
                raw_test_block=raw_test_block,
                test_index=test_index,
            )
        )

    _validate_test_names(file_path=file_path, blocks=tuple(discovered_blocks))
    return tuple(discovered_blocks)


def _split_sql_test_blocks(*, file_path: Path, contents: str) -> tuple[str, ...]:
    matches: tuple[re.Match[str], ...] = tuple(TEST_HEADER_ONLY_PATTERN.finditer(contents))
    if not matches:
        return ()
    if contents[: matches[0].start()].strip():
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )

    raw_blocks: list[str] = []
    match_index: int
    match: re.Match[str]
    for match_index, match in enumerate(matches):
        next_start: int = (
            matches[match_index + 1].start() if match_index + 1 < len(matches) else len(contents)
        )
        raw_blocks.append(contents[match.start() : next_start].strip())
    return tuple(raw_blocks)


def _parse_single_sql_test_block(
    *,
    file_path: Path,
    raw_test_block: str,
    test_index: int,
) -> DiscoveredSqlTestBlock:
    header_match: re.Match[str] | None = TEST_HEADER_PATTERN.match(raw_test_block)
    if header_match is None:
        raise SqlTestParseError(
            f"SQL test '{file_path}' must start with a TEST() header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, object] = _parse_test_header(
        header=header_match.group("header"),
        file_path=file_path,
    )
    sql_body: str = cleandoc(header_match.group("sql"))
    if not sql_body:
        raise SqlTestParseError(f"SQL test '{file_path}' must define SQL after TEST(...)")

    name_value: object | None = header_values.get("name")
    test_name: str | None = cast(str | None, name_value)
    mode_value: object = header_values.get("mode", DEFAULT_SQL_TEST_MODE.value)
    test_mode: SqlTestMode = SqlTestMode(str(mode_value))
    return DiscoveredSqlTestBlock(
        test_index=test_index,
        header_values=header_values,
        sql_body=sql_body,
        name=test_name,
        mode=test_mode,
    )


def _parse_test_header(*, header: str, file_path: Path) -> dict[str, object]:
    stripped_header: str = header.strip()
    if not stripped_header:
        return {}

    try:
        parsed_header: object = yaml.safe_load(f"{{{stripped_header}}}")
    except YAMLError as error:
        raise SqlTestParseError(
            f"TEST() header in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(parsed_header, dict) or not all(
        isinstance(key, str) for key in parsed_header
    ):
        raise SqlTestParseError(
            f"TEST() header in '{file_path}' must be a mapping like `TEST (name: \"...\");`"
        )

    supported_keys: frozenset[str] = frozenset({"name", "mode"})
    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in parsed_header if key not in supported_keys
    )
    if unsupported_keys:
        raise SqlTestParseError(
            f"TEST() in '{file_path}' only supports `name` and `mode`; unsupported keys: "
            f"{', '.join(unsupported_keys)}"
        )

    _validate_test_name(name_value=parsed_header.get("name"), file_path=file_path)
    _validate_test_mode(mode_value=parsed_header.get("mode"), file_path=file_path)

    return cast(dict[str, object], parsed_header)


def _validate_test_name(*, name_value: object | None, file_path: Path) -> None:
    if name_value is None:
        return
    if not isinstance(name_value, str) or not name_value.strip():
        raise SqlTestParseError(f"TEST() name in '{file_path}' must be a non-empty string")


def _validate_test_mode(*, mode_value: object | None, file_path: Path) -> None:
    if mode_value is None:
        return
    if not isinstance(mode_value, str):
        raise SqlTestParseError(f"TEST() mode in '{file_path}' must be a string")

    allowed_modes: str = ", ".join(mode.value for mode in SqlTestMode)
    if mode_value not in {mode.value for mode in SqlTestMode}:
        raise SqlTestParseError(f"TEST() mode in '{file_path}' must be one of: {allowed_modes}")


def _validate_test_names(*, file_path: Path, blocks: tuple[DiscoveredSqlTestBlock, ...]) -> None:
    if len(blocks) <= 1:
        return

    unnamed_indexes: tuple[int, ...] = tuple(
        block.test_index for block in blocks if block.name is None
    )
    if unnamed_indexes:
        missing_indexes: str = ", ".join(str(index) for index in unnamed_indexes)
        raise SqlTestParseError(
            f"SQL test '{file_path}' contains multiple TEST blocks; every block must define "
            f"a unique `name`. Missing names for blocks: {missing_indexes}"
        )

    seen_names: set[str] = set()
    block: DiscoveredSqlTestBlock
    for block in blocks:
        if block.name is None:
            raise SqlTestParseError(
                f"SQL test '{file_path}' contains multiple TEST blocks; every block must define "
                "a unique `name`"
            )
        if block.name in seen_names:
            raise SqlTestParseError(
                f"SQL test '{file_path}' defines duplicate TEST() name '{block.name}'"
            )
        seen_names.add(block.name)
