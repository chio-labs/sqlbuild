"""Parsing helpers for authored SQL audit files."""

from __future__ import annotations

import re
from inspect import cleandoc
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from sqlbuild.compiler.discovery.exceptions import SqlAuditParseError
from sqlbuild.compiler.discovery.helpers.constants import (
    AUDIT_HEADER_ONLY_PATTERN,
    AUDIT_HEADER_PATTERN,
)
from sqlbuild.compiler.discovery.models import DiscoveredAuditBlock


def parse_sql_audit_file(contents: str, file_path: Path) -> tuple[DiscoveredAuditBlock, ...]:
    """Parse one SQL audit file into one or more raw AUDIT(...) blocks."""

    raw_audit_blocks: tuple[str, ...] = _split_sql_audit_blocks(
        file_path=file_path, contents=contents
    )
    if not raw_audit_blocks:
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' must start with an AUDIT() header as the first "
            "non-whitespace content"
        )

    discovered_blocks: list[DiscoveredAuditBlock] = []
    audit_index: int
    raw_audit_block: str
    for audit_index, raw_audit_block in enumerate(raw_audit_blocks, start=1):
        discovered_blocks.append(
            _parse_single_sql_audit_block(
                file_path=file_path,
                raw_audit_block=raw_audit_block,
                audit_index=audit_index,
            )
        )

    _validate_audit_names(file_path=file_path, blocks=tuple(discovered_blocks))
    return tuple(discovered_blocks)


def _split_sql_audit_blocks(*, file_path: Path, contents: str) -> tuple[str, ...]:
    matches: tuple[re.Match[str], ...] = tuple(AUDIT_HEADER_ONLY_PATTERN.finditer(contents))
    if not matches:
        return ()
    if contents[: matches[0].start()].strip():
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' must start with an AUDIT() header as the first "
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


def _parse_single_sql_audit_block(
    *,
    file_path: Path,
    raw_audit_block: str,
    audit_index: int,
) -> DiscoveredAuditBlock:
    header_match: re.Match[str] | None = AUDIT_HEADER_PATTERN.match(raw_audit_block)
    if header_match is None:
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' must start with an AUDIT() header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, object] = _parse_audit_header(
        header=header_match.group("header"),
        file_path=file_path,
    )
    sql_body: str = cleandoc(header_match.group("sql"))
    if not sql_body:
        raise SqlAuditParseError(f"SQL audit '{file_path}' must define SQL after AUDIT(...)")

    name_value: object | None = header_values.get("name")
    audit_name: str | None = cast(str | None, name_value)
    return DiscoveredAuditBlock(
        audit_index=audit_index,
        header_values=header_values,
        sql_body=sql_body,
        name=audit_name,
    )


def _parse_audit_header(*, header: str, file_path: Path) -> dict[str, object]:
    stripped_header: str = header.strip()
    if not stripped_header:
        return {}

    try:
        parsed_header: object = yaml.safe_load(f"{{{stripped_header}}}")
    except YAMLError as error:
        raise SqlAuditParseError(
            f"AUDIT() header in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(parsed_header, dict) or not all(
        isinstance(key, str) for key in parsed_header
    ):
        raise SqlAuditParseError(
            f"AUDIT() header in '{file_path}' must be a mapping like `AUDIT (name: \"...\");`"
        )

    unsupported_keys: tuple[str, ...] = tuple(str(key) for key in parsed_header if key != "name")
    if unsupported_keys:
        raise SqlAuditParseError(
            f"AUDIT() in '{file_path}' only supports `name` right now; unsupported keys: "
            f"{', '.join(unsupported_keys)}"
        )

    name_value: object | None = parsed_header.get("name")
    if name_value is not None and (not isinstance(name_value, str) or not name_value.strip()):
        raise SqlAuditParseError(f"AUDIT() name in '{file_path}' must be a non-empty string")

    return cast(dict[str, object], parsed_header)


def _validate_audit_names(*, file_path: Path, blocks: tuple[DiscoveredAuditBlock, ...]) -> None:
    if len(blocks) <= 1:
        return

    unnamed_indexes: tuple[int, ...] = tuple(
        block.audit_index for block in blocks if block.name is None
    )
    if unnamed_indexes:
        missing_indexes: str = ", ".join(str(index) for index in unnamed_indexes)
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' contains multiple AUDIT blocks; every block must define "
            f"a unique `name`. Missing names for blocks: {missing_indexes}"
        )

    seen_names: set[str] = set()
    block: DiscoveredAuditBlock
    for block in blocks:
        if block.name is None:
            raise SqlAuditParseError(
                f"SQL audit '{file_path}' contains multiple AUDIT blocks; every block must define "
                "a unique `name`"
            )
        if block.name in seen_names:
            raise SqlAuditParseError(
                f"SQL audit '{file_path}' defines duplicate AUDIT() name '{block.name}'"
            )
        seen_names.add(block.name)
