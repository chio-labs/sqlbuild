"""Parsing helpers for authored SQL audit files."""

from __future__ import annotations

from collections.abc import Iterator
from inspect import cleandoc
from pathlib import Path
from typing import cast

from sqlbuild.compiler.auditing.models import MeasurementContract
from sqlbuild.compiler.auditing.types import AuditEvaluationMode
from sqlbuild.compiler.discovery._helpers.sql.model_files import parse_header_values
from sqlbuild.compiler.discovery.exceptions import SqlAuditParseError
from sqlbuild.compiler.discovery.models import DiscoveredAuditBlock

_AUDIT_NAME_HEADER_KEY: str = "name"
_AUDIT_SEVERITY_HEADER_KEY: str = "severity"
_AUDIT_RUN_SCOPE_HEADER_KEY: str = "run_scope"
_AUDIT_ALWAYS_RUN_HEADER_KEY: str = "always_run"
_AUDIT_EVALUATION_HEADER_KEY: str = "evaluation"
_AUDIT_VALUE_HEADER_KEY: str = "value"
_AUDIT_SAMPLE_COUNT_HEADER_KEY: str = "sample_count"
_AUDIT_SAMPLE_UNIT_HEADER_KEY: str = "sample_unit"
_AUDIT_THRESHOLDS_HEADER_KEY: str = "thresholds"
_AUDIT_MINIMUM_SAMPLES_HEADER_KEY: str = "minimum_samples"
_OPEN_PAREN: str = "("
_CLOSE_PAREN: str = ")"
_STATEMENT_DELIMITER: str = ";"
_IDENTIFIER_SEPARATOR: str = "_"
_ESCAPE_CHARACTER: str = "\\"
_SQL_QUOTES: frozenset[str] = frozenset({"'", '"', "`"})
_SUPPORTED_AUDIT_HEADER_KEYS: frozenset[str] = frozenset(
    {
        _AUDIT_NAME_HEADER_KEY,
        _AUDIT_SEVERITY_HEADER_KEY,
        _AUDIT_RUN_SCOPE_HEADER_KEY,
        _AUDIT_ALWAYS_RUN_HEADER_KEY,
        _AUDIT_EVALUATION_HEADER_KEY,
        _AUDIT_VALUE_HEADER_KEY,
        _AUDIT_SAMPLE_COUNT_HEADER_KEY,
        _AUDIT_SAMPLE_UNIT_HEADER_KEY,
        _AUDIT_THRESHOLDS_HEADER_KEY,
        _AUDIT_MINIMUM_SAMPLES_HEADER_KEY,
    }
)


def parse_sql_audit_file(*, contents: str, file_path: Path) -> tuple[DiscoveredAuditBlock, ...]:
    """Parse one SQL audit file into one or more raw AUDIT(...) blocks."""

    starts: tuple[int, ...] = _find_top_level_keywords(text=contents, keyword="AUDIT")
    if not starts or contents[: starts[0]].strip():
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' must start with an AUDIT() header as the first "
            "non-whitespace content"
        )
    blocks: list[DiscoveredAuditBlock] = []
    for index, start in enumerate(starts, start=1):
        end: int = starts[index] if index < len(starts) else len(contents)
        blocks.append(
            _parse_single_sql_audit_block(
                file_path=file_path,
                raw_audit_block=contents[start:end].strip(),
                audit_index=index,
            )
        )
    result: tuple[DiscoveredAuditBlock, ...] = tuple(blocks)
    _validate_audit_names(file_path=file_path, blocks=result)
    return result


def _parse_single_sql_audit_block(
    *, file_path: Path, raw_audit_block: str, audit_index: int
) -> DiscoveredAuditBlock:
    open_index: int = _keyword_open_paren(
        text=raw_audit_block, keyword="AUDIT", file_path=file_path
    )
    close_index: int = _find_matching_parenthesis(
        text=raw_audit_block,
        open_index=open_index,
        file_path=file_path,
        label="AUDIT",
    )
    body_start: int = _consume_delimiter(
        text=raw_audit_block,
        start=close_index + 1,
        file_path=file_path,
        label="AUDIT(...) header",
    )
    header_values: dict[str, object] = _parse_audit_header(
        header=raw_audit_block[open_index + 1 : close_index], file_path=file_path
    )
    evaluation_mode: AuditEvaluationMode = _parse_evaluation_mode(
        header_values=header_values, file_path=file_path
    )
    body: str = raw_audit_block[body_start:]
    measure_sql: str | None = None
    evidence_sql: str | None = None
    contract: MeasurementContract | None = None
    if evaluation_mode == AuditEvaluationMode.MEASUREMENT:
        measure_sql, evidence_sql = _parse_measurement_body(body=body, file_path=file_path)
        contract = MeasurementContract(
            value_column=cast(str, header_values[_AUDIT_VALUE_HEADER_KEY]),
            sample_count_column=cast(str | None, header_values.get(_AUDIT_SAMPLE_COUNT_HEADER_KEY)),
            sample_unit=cast(str | None, header_values.get(_AUDIT_SAMPLE_UNIT_HEADER_KEY)),
        )
        sql_body: str = measure_sql
    else:
        sql_body = cleandoc(body)
        if not sql_body:
            raise SqlAuditParseError(f"SQL audit '{file_path}' must define SQL after AUDIT(...)")
        body_code_start: int = _skip_space_and_comments(text=sql_body, start=0)
        if body_code_start in (
            *_find_top_level_keywords(text=sql_body, keyword="MEASURE"),
            *_find_top_level_keywords(text=sql_body, keyword="EVIDENCE"),
        ):
            raise SqlAuditParseError(
                f"Violation audit '{file_path}' must use a bare SELECT body, not MEASURE/EVIDENCE"
            )

    return DiscoveredAuditBlock(
        audit_index=audit_index,
        header_values=header_values,
        sql_body=sql_body,
        name=cast(str | None, header_values.get(_AUDIT_NAME_HEADER_KEY)),
        evaluation_mode=evaluation_mode,
        measurement_contract=contract,
        measure_sql=measure_sql,
        evidence_sql=evidence_sql,
    )


def _parse_audit_header(*, header: str, file_path: Path) -> dict[str, object]:
    parsed_header: dict[str, object] = parse_header_values(
        header=header,
        file_path=file_path,
        statement_name="AUDIT",
        error_class=SqlAuditParseError,
    )
    unsupported_keys: tuple[str, ...] = tuple(
        str(key) for key in parsed_header if key not in _SUPPORTED_AUDIT_HEADER_KEYS
    )
    if unsupported_keys:
        raise SqlAuditParseError(
            f"AUDIT() in '{file_path}' has unsupported keys: {', '.join(unsupported_keys)}"
        )
    for key in (
        _AUDIT_NAME_HEADER_KEY,
        _AUDIT_SEVERITY_HEADER_KEY,
        _AUDIT_RUN_SCOPE_HEADER_KEY,
        _AUDIT_EVALUATION_HEADER_KEY,
        _AUDIT_VALUE_HEADER_KEY,
        _AUDIT_SAMPLE_COUNT_HEADER_KEY,
        _AUDIT_SAMPLE_UNIT_HEADER_KEY,
    ):
        value: object | None = parsed_header.get(key)
        if key in parsed_header and (not isinstance(value, str) or not value.strip()):
            raise SqlAuditParseError(f"AUDIT() {key} in '{file_path}' must be a non-empty string")
    always_run: object | None = parsed_header.get(_AUDIT_ALWAYS_RUN_HEADER_KEY)
    if _AUDIT_ALWAYS_RUN_HEADER_KEY in parsed_header and not isinstance(always_run, bool):
        raise SqlAuditParseError(f"AUDIT() always_run in '{file_path}' must be a boolean")
    return parsed_header


def _parse_evaluation_mode(
    *, header_values: dict[str, object], file_path: Path
) -> AuditEvaluationMode:
    raw_mode: object = header_values.get(
        _AUDIT_EVALUATION_HEADER_KEY, AuditEvaluationMode.VIOLATIONS.value
    )
    try:
        mode: AuditEvaluationMode = AuditEvaluationMode(cast(str, raw_mode))
    except ValueError as error:
        raise SqlAuditParseError(
            f"AUDIT() evaluation in '{file_path}' must be one of: violations, measurement"
        ) from error
    measurement_only_keys: tuple[str, ...] = (
        _AUDIT_VALUE_HEADER_KEY,
        _AUDIT_SAMPLE_COUNT_HEADER_KEY,
        _AUDIT_SAMPLE_UNIT_HEADER_KEY,
        _AUDIT_THRESHOLDS_HEADER_KEY,
        _AUDIT_MINIMUM_SAMPLES_HEADER_KEY,
    )
    if mode == AuditEvaluationMode.VIOLATIONS:
        invalid: tuple[str, ...] = tuple(
            key for key in measurement_only_keys if key in header_values
        )
        if invalid:
            raise SqlAuditParseError(
                f"Violation audit '{file_path}' must not define measurement keys: "
                f"{', '.join(invalid)}"
            )
    elif _AUDIT_VALUE_HEADER_KEY not in header_values:
        raise SqlAuditParseError(f"Measurement audit '{file_path}' must define `value`")
    return mode


def _parse_measurement_body(*, body: str, file_path: Path) -> tuple[str, str | None]:
    position: int = _skip_space_and_comments(text=body, start=0)
    measure_sql, position = _extract_delimited_query(
        text=body, position=position, keyword="MEASURE", file_path=file_path, required=True
    )
    position = _skip_space_and_comments(text=body, start=position)
    evidence_sql: str | None = None
    if _keyword_at(text=body, keyword="EVIDENCE", position=position):
        evidence_sql, position = _extract_delimited_query(
            text=body, position=position, keyword="EVIDENCE", file_path=file_path, required=False
        )
        position = _skip_space_and_comments(text=body, start=position)
    if position != len(body):
        label: str = (
            "duplicate MEASURE/EVIDENCE block"
            if _keyword_at_any(text=body, position=position, keywords=("MEASURE", "EVIDENCE"))
            else "bare SQL outside MEASURE/EVIDENCE blocks"
        )
        raise SqlAuditParseError(f"Measurement audit '{file_path}' has {label}")
    return cast(str, measure_sql), evidence_sql


def _extract_delimited_query(
    *, text: str, position: int, keyword: str, file_path: Path, required: bool
) -> tuple[str | None, int]:
    if not _keyword_at(text=text, keyword=keyword, position=position):
        if required:
            raise SqlAuditParseError(
                f"Measurement audit '{file_path}' must define exactly one MEASURE(...) block"
            )
        return None, position
    open_index: int = (
        _keyword_open_paren(text=text[position:], keyword=keyword, file_path=file_path) + position
    )
    close_index: int = _find_matching_parenthesis(
        text=text, open_index=open_index, file_path=file_path, label=keyword
    )
    query: str = cleandoc(text[open_index + 1 : close_index])
    _validate_single_query(query=query, file_path=file_path, label=keyword)
    end: int = _consume_delimiter(
        text=text, start=close_index + 1, file_path=file_path, label=f"{keyword}(...) block"
    )
    return query, end


def _validate_single_query(*, query: str, file_path: Path, label: str) -> None:
    if not query:
        raise SqlAuditParseError(f"{label}(...) in '{file_path}' must contain one SELECT query")
    start: int = _skip_space_and_comments(text=query, start=0)
    if not (
        _keyword_at(text=query, keyword="SELECT", position=start)
        or _keyword_at(text=query, keyword="WITH", position=start)
    ):
        raise SqlAuditParseError(f"{label}(...) in '{file_path}' must contain one SELECT query")
    semicolons: tuple[int, ...] = _top_level_semicolons(query)
    if semicolons and (len(semicolons) > 1 or query[semicolons[0] + 1 :].strip()):
        raise SqlAuditParseError(f"{label}(...) in '{file_path}' must contain exactly one query")


def _keyword_open_paren(*, text: str, keyword: str, file_path: Path) -> int:
    start: int = _skip_space_and_comments(text=text, start=0)
    if not _keyword_at(text=text, keyword=keyword, position=start):
        raise SqlAuditParseError(f"SQL audit '{file_path}' must start with {keyword}(...)")
    position: int = _skip_space_and_comments(text=text, start=start + len(keyword))
    if position >= len(text) or text[position] != _OPEN_PAREN:
        raise SqlAuditParseError(f"SQL audit '{file_path}' must start with {keyword}(...)")
    return position


def _consume_delimiter(*, text: str, start: int, file_path: Path, label: str) -> int:
    position: int = _skip_space_and_comments(text=text, start=start)
    if position >= len(text) or text[position] != _STATEMENT_DELIMITER:
        raise SqlAuditParseError(f"{label} in '{file_path}' must end with `);`")
    return position + 1


def _find_matching_parenthesis(*, text: str, open_index: int, file_path: Path, label: str) -> int:
    depth: int = 1
    for index, character in _code_characters(text=text, start=open_index + 1):
        if character == _OPEN_PAREN:
            depth += 1
        elif character == _CLOSE_PAREN:
            depth -= 1
            if depth == 0:
                return index
    raise SqlAuditParseError(f"Unclosed {label}(...) block in '{file_path}'")


def _find_top_level_keywords(*, text: str, keyword: str) -> tuple[int, ...]:
    depth: int = 0
    found: list[int] = []
    for index, character in _code_characters(text=text, start=0):
        if character == _OPEN_PAREN:
            depth += 1
        elif character == _CLOSE_PAREN:
            depth = max(0, depth - 1)
        elif (
            depth == 0
            and character.upper() == keyword[0]
            and _keyword_at(text=text, keyword=keyword, position=index)
        ):
            after: int = _skip_space_and_comments(text=text, start=index + len(keyword))
            if after < len(text) and text[after] == _OPEN_PAREN:
                found.append(index)
    return tuple(found)


def _top_level_semicolons(text: str) -> tuple[int, ...]:
    depth: int = 0
    found: list[int] = []
    for index, character in _code_characters(text=text, start=0):
        if character == _OPEN_PAREN:
            depth += 1
        elif character == _CLOSE_PAREN:
            depth = max(0, depth - 1)
        elif character == _STATEMENT_DELIMITER and depth == 0:
            found.append(index)
    return tuple(found)


def _code_characters(*, text: str, start: int) -> Iterator[tuple[int, str]]:
    """Yield code characters while skipping quoted text and SQL comments."""

    index: int = start
    while index < len(text):
        character: str = text[index]
        if text.startswith("--", index):
            newline: int = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            close: int = text.find("*/", index + 2)
            index = len(text) if close < 0 else close + 2
            continue
        if character in _SQL_QUOTES:
            quote: str = character
            index += 1
            while index < len(text):
                if text[index] == quote:
                    if index + 1 < len(text) and text[index + 1] == quote:
                        index += 2
                        continue
                    index += 1
                    break
                if text[index] == _ESCAPE_CHARACTER:
                    index += 2
                else:
                    index += 1
            continue
        yield index, character
        index += 1


def _skip_space_and_comments(*, text: str, start: int) -> int:
    position: int = start
    while position < len(text):
        if text[position].isspace():
            position += 1
        elif text.startswith("--", position):
            newline: int = text.find("\n", position + 2)
            position = len(text) if newline < 0 else newline + 1
        elif text.startswith("/*", position):
            close: int = text.find("*/", position + 2)
            position = len(text) if close < 0 else close + 2
        else:
            break
    return position


def _keyword_at(*, text: str, keyword: str, position: int) -> bool:
    end: int = position + len(keyword)
    if text[position:end].upper() != keyword:
        return False
    before: str = text[position - 1] if position > 0 else " "
    after: str = text[end] if end < len(text) else " "
    return not (before.isalnum() or before == _IDENTIFIER_SEPARATOR) and not (
        after.isalnum() or after == _IDENTIFIER_SEPARATOR
    )


def _keyword_at_any(*, text: str, position: int, keywords: tuple[str, ...]) -> bool:
    return any(_keyword_at(text=text, keyword=keyword, position=position) for keyword in keywords)


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
    for block in blocks:
        if block.name in seen_names:
            raise SqlAuditParseError(
                f"SQL audit '{file_path}' defines duplicate AUDIT() name '{block.name}'"
            )
        seen_names.add(cast(str, block.name))
