"""Point SQL-test extraction errors and malformed calls at the authored text they are about."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.refs.references import (
    reference_call_location,
    reference_call_syntax_key,
    scan_sql_reference_calls,
)
from sqlbuild.compiler.compile._helpers.sql_tests.native import (
    authored_sql_test_cte_batch,
    authored_sql_test_ctes,
)
from sqlbuild.compiler.compile.constants import REFERENCE_CALL_SYNTAX_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError, SqlTestExtractionError
from sqlbuild.compiler.compile.models import CompilerDiagnostic, SqlReferenceScan
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import SourceLocation

_TAB_SIZE: int = 8
_LINE_BREAK: str = "\n"
_CARRIAGE_RETURN: str = "\r"
_TAB: str = "\t"


@dataclass(frozen=True)
class _CleanedLine:
    """One line of `inspect.cleandoc` output and where it comes from in the authored text."""

    authored_start: int
    authored_text: str
    removed_columns: int


def validate_authored_test_cte_names(
    *, test_files: tuple[DiscoveredSqlTestFile, ...], syntax: SqlLexicalSyntax
) -> None:
    """Raise the located CTE-name error of the first authored test block that has one."""

    blocks: list[tuple[DiscoveredSqlTestFile, DiscoveredSqlTestBlock]] = []
    test_file: DiscoveredSqlTestFile
    for test_file in test_files:
        blocks.extend((test_file, test_block) for test_block in test_file.blocks)
    try:
        _ = authored_sql_test_cte_batch(
            tests=tuple(
                (test_block.sql_body, str(test_file.relative_path))
                for test_file, test_block in blocks
            ),
            syntax=syntax,
        )
    except SqlTestExtractionError as error:
        failed_file, failed_block = blocks[error.test_index]
        raise located_extraction_error(
            error=error, test_file=failed_file, test_block=failed_block, sql=failed_block.sql_body
        ) from None


def validate_authored_scenario_cte_names(
    *, scenario_files: tuple[DiscoveredSqlScenarioFile, ...], syntax: SqlLexicalSyntax
) -> None:
    """Raise the located CTE-name or materialization error of the first scenario that has one."""

    try:
        _ = authored_sql_test_cte_batch(
            tests=tuple(
                (scenario_file.sql_body, str(scenario_file.relative_path))
                for scenario_file in scenario_files
            ),
            syntax=syntax,
            scenarios=True,
        )
    except SqlTestExtractionError as error:
        failed: DiscoveredSqlScenarioFile = scenario_files[error.test_index]
        offset: int | None = (
            _authored_offset(
                contents=failed.contents,
                authored=failed.sql_body,
                span=failed.sql_body_span,
                body_offset=error.token_offset,
            )
            if error.token_offset is not None
            else None
        )
        raise _located_error(
            error=error, contents=failed.contents, relative_path=failed.relative_path, offset=offset
        ) from None


def located_extraction_error(
    *,
    error: SqlTestExtractionError,
    test_file: DiscoveredSqlTestFile,
    test_block: DiscoveredSqlTestBlock,
    sql: str,
) -> CompileInputError:
    """Return the error at the file line and column of its offending text when that is exact."""

    offset: int | None = (
        authored_file_offset(
            test_file=test_file, test_block=test_block, body_offset=error.token_offset
        )
        if error.token_offset is not None and sql == test_block.sql_body
        else None
    )
    return _located_error(
        error=error,
        contents=test_file.contents,
        relative_path=test_file.relative_path,
        offset=offset,
    )


def _located_error(
    *, error: SqlTestExtractionError, contents: str, relative_path: Path, offset: int | None
) -> CompileInputError:
    if offset is None:
        return CompileInputError(
            error.message, code=error.code, help=error.help, bridge_independent=True
        )
    line: int = contents.count(_LINE_BREAK, 0, offset) + 1
    column: int = offset - (contents.rfind(_LINE_BREAK, 0, offset) + 1) + 1
    return CompileInputError(
        f"{error.message}\n  --> {relative_path.as_posix()}:{line}:{column}",
        code=error.code,
        help=error.help,
        bridge_independent=True,
    )


def report_authored_invalid_calls(
    *,
    test_file: DiscoveredSqlTestFile,
    test_block: DiscoveredSqlTestBlock,
    actual_cte_name: str,
    syntax: SqlLexicalSyntax,
) -> int:
    """Report each malformed reference call outside the actual CTE at its own location."""

    ctes: tuple[tuple[str, int, str], ...] = authored_sql_test_ctes(
        sql=test_block.sql_body, file_label=str(test_file.relative_path), syntax=syntax
    )
    reported: int = 0
    name: str
    body_start: int
    body: str
    for name, body_start, body in ctes:
        if name == actual_cte_name:
            continue
        scan: SqlReferenceScan = scan_sql_reference_calls(sql=body, syntax=syntax)
        for invalid_call in scan.invalid_calls:
            offset: int | None = authored_file_offset(
                test_file=test_file,
                test_block=test_block,
                body_offset=body_start + invalid_call.start,
            )
            if offset is None:
                return reported
            location: SourceLocation = reference_call_location(
                path=test_file.relative_path,
                text=test_file.contents,
                start=offset,
                call=invalid_call.call,
            )
            report_compile_diagnostic(
                key=reference_call_syntax_key(
                    file_path=test_file.file_path, call=invalid_call.call, location=location
                ),
                diagnostic=CompilerDiagnostic(
                    phase=DiagnosticPhase.COMPILE,
                    severity=DiagnosticSeverity.ERROR,
                    code=REFERENCE_CALL_SYNTAX_CODE,
                    message=invalid_call.message,
                    location=location,
                    help=invalid_call.help,
                ),
            )
            reported += 1
    return reported


def authored_file_offset(
    *, test_file: DiscoveredSqlTestFile, test_block: DiscoveredSqlTestBlock, body_offset: int
) -> int | None:
    """Map an offset in a block's cleaned SQL back to the file, or None if it cannot be exact."""

    return _authored_offset(
        contents=test_file.contents,
        authored=test_block.sql_body,
        span=test_block.sql_body_span,
        body_offset=body_offset,
    )


def _authored_offset(
    *, contents: str, authored: str, span: tuple[int, int] | None, body_offset: int
) -> int | None:
    if span is None:
        return None
    lines: tuple[_CleanedLine, ...] | None = _cleaned_lines(
        authored=authored, span=span, contents=contents
    )
    if lines is None:
        return None
    body: str = authored
    line_index: int = body.count(_LINE_BREAK, 0, body_offset)
    column: int = body_offset - (body.rfind(_LINE_BREAK, 0, body_offset) + 1)
    cleaned: _CleanedLine = lines[line_index]
    return cleaned.authored_start + _authored_index(
        text=cleaned.authored_text, expanded_column=cleaned.removed_columns + column
    )


def _cleaned_lines(
    *, authored: str, span: tuple[int, int], contents: str
) -> tuple[_CleanedLine, ...] | None:
    text: str = contents[span[0] : span[1]]
    raw_lines: list[str] = text.split(_LINE_BREAK)
    expanded: list[str] = [line.expandtabs(_TAB_SIZE) for line in raw_lines]
    indents: list[int] = [len(line) - len(line.lstrip()) for line in expanded[1:] if line.strip()]
    margin: int = min(indents, default=sys.maxsize)
    starts: list[int] = []
    cursor: int = span[0]
    for line in raw_lines:
        starts.append(cursor)
        cursor += len(line) + 1
    removed: list[int] = [
        len(expanded[0]) - len(expanded[0].lstrip()),
        *([margin if margin < sys.maxsize else 0] * (len(expanded) - 1)),
    ]
    kept: list[int] = list(range(len(expanded)))
    while kept and not expanded[kept[-1]][removed[kept[-1]] :]:
        kept.pop()
    while kept and not expanded[kept[0]][removed[kept[0]] :]:
        kept.pop(0)
    cleaned: str = _LINE_BREAK.join(expanded[index][removed[index] :] for index in kept)
    if cleaned != authored:
        return None
    return tuple(
        _CleanedLine(
            authored_start=starts[index],
            authored_text=raw_lines[index],
            removed_columns=removed[index],
        )
        for index in kept
    )


def _authored_index(*, text: str, expanded_column: int) -> int:
    position: int = 0
    column: int = 0
    index: int
    character: str
    for index, character in enumerate(text):
        width: int = _TAB_SIZE - column % _TAB_SIZE if character == _TAB else 1
        if expanded_column < position + width:
            return index
        position += width
        column = 0 if character == _CARRIAGE_RETURN else column + width
    return len(text)
