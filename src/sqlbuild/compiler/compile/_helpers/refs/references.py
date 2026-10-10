"""Logical SQL reference extraction helpers for compile semantics."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.refs.native import extract_native_sql_references
from sqlbuild.compiler.compile._helpers.render.spans import map_through_passes
from sqlbuild.compiler.compile.constants import (
    REFERENCE_CALL_SYNTAX_CODE,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    CompileSqlReference,
    ExpansionSpan,
    InvalidSqlReferenceCall,
    MappedOffset,
    SqlReferenceOrigin,
    SqlReferenceScan,
    SqlReferenceSourceMap,
)
from sqlbuild.compiler.compile.types import (
    DiagnosticPhase,
    DiagnosticSeverity,
    SqlReferenceScanFailure,
)
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import SourceLocation


def extract_sql_references(
    *, sql: str, syntax: SqlLexicalSyntax, origin: SqlReferenceOrigin | None = None
) -> tuple[CompileSqlReference, ...]:
    """Return logical SQL refs outside comments and quotes, reporting rejected calls as P012."""

    scan: SqlReferenceScan = scan_sql_reference_calls(sql=sql, syntax=syntax, origin=origin)
    report_invalid_reference_calls(invalid_calls=scan.invalid_calls, origin=origin, syntax=syntax)
    return scan.references


def scan_sql_reference_calls(
    *, sql: str, syntax: SqlLexicalSyntax, origin: SqlReferenceOrigin | None = None
) -> SqlReferenceScan:
    """Return valid references and rejected calls; a scan error is located in `origin`."""

    outcome: SqlReferenceScan | SqlReferenceScanFailure = _reference_scan_outcome(
        sql=sql, syntax=syntax
    )
    if isinstance(outcome, SqlReferenceScan):
        return outcome
    raise _located_scan_error(failure=outcome, sql=sql, origin=origin, syntax=syntax)


def _reference_scan_outcome(
    *, sql: str, syntax: SqlLexicalSyntax
) -> SqlReferenceScan | SqlReferenceScanFailure:
    outcome: SqlReferenceScan | SqlReferenceScanFailure = extract_native_sql_references(
        sql=sql, syntax=syntax
    )
    report_native_answer(stage=NativeStage.REFERENCE_EXTRACTION, kind="reference_scans")
    return outcome


def _located_scan_error(
    *,
    failure: SqlReferenceScanFailure,
    sql: str,
    origin: SqlReferenceOrigin | None,
    syntax: SqlLexicalSyntax,
) -> CompileInputError:
    """Locate a scan error in authored text; unmapped or expansion-shaped faults stay unlocated."""

    message, start = failure
    if origin is None:
        return CompileInputError(message)
    authored_offset: int | None = _authored_fault_offset(
        failure=failure, sql=sql, origin=origin, syntax=syntax
    )
    path: str = origin.relative_path.as_posix()
    if authored_offset is None:
        return CompileInputError(f"{path}: {message}")
    contents: str = origin.contents
    line: int = contents.count("\n", 0, authored_offset) + 1
    column: int = authored_offset - (contents.rfind("\n", 0, authored_offset) + 1) + 1
    return CompileInputError(f"{path}:{line}:{column}: {message}")


def _authored_fault_offset(
    *,
    failure: SqlReferenceScanFailure,
    sql: str,
    origin: SqlReferenceOrigin,
    syntax: SqlLexicalSyntax,
) -> int | None:
    """Map the fault to authored text unless expansion output produced or shaped the failure."""

    source_map: SqlReferenceSourceMap | None = origin.source_map
    start: int = failure[1]
    body_start: int | None = source_map.body_start() if source_map is not None else None
    if source_map is None or body_start is None or start >= len(sql):
        return None
    mapped: MappedOffset = map_through_passes(offset=start, passes=source_map.passes)
    authored_offset: int = body_start + mapped.offset
    if (
        mapped.generated
        or authored_offset >= len(origin.contents)
        or origin.contents[authored_offset] != sql[start]
    ):
        return None
    blanked: list[str] = list(sql)
    for output_start, output_end in _expansion_output_ranges(source_map.passes):
        blanked[output_start:output_end] = " " * (output_end - output_start)
    if _reference_scan_outcome(sql="".join(blanked), syntax=syntax) != failure:
        return None
    return authored_offset


def _expansion_output_ranges(
    passes: tuple[tuple[ExpansionSpan, ...], ...],
) -> list[tuple[int, int]]:
    """Return every expansion's output range in the coordinates of the final pass's output."""

    ranges: list[tuple[int, int]] = []
    for index, spans in enumerate(passes):
        for span in spans:
            output_start: int = span.output_start
            output_end: int = span.output_end
            for later_spans in passes[index + 1 :]:
                output_start = _later_pass_offset(offset=output_start, spans=later_spans, end=False)
                output_end = _later_pass_offset(offset=output_end, spans=later_spans, end=True)
            ranges.append((output_start, output_end))
    return ranges


def _later_pass_offset(*, offset: int, spans: tuple[ExpansionSpan, ...], end: bool) -> int:
    """Carry a range boundary through one later pass, widening it over a span that covers it."""

    shift: int = 0
    for span in spans:
        if offset < span.source_start or (end and offset == span.source_start):
            break
        if offset < span.source_end or (end and offset == span.source_end):
            return span.output_end if end else span.output_start
        shift += (span.output_end - span.output_start) - (span.source_end - span.source_start)
    return offset + shift


def report_invalid_reference_calls(
    *,
    invalid_calls: tuple[InvalidSqlReferenceCall, ...],
    origin: SqlReferenceOrigin | None,
    syntax: SqlLexicalSyntax,
) -> None:
    """Report each rejected reference call at its authored location when one is known."""

    if not invalid_calls:
        return
    authored_starts: dict[str, list[int]] = _authored_invalid_call_starts(
        origin=origin, syntax=syntax
    )
    seen: dict[str, int] = {}
    for invalid_call in invalid_calls:
        occurrence: int = seen.get(invalid_call.call, 0)
        seen[invalid_call.call] = occurrence + 1
        starts: list[int] = authored_starts.get(invalid_call.call, [])
        location: SourceLocation | None = (
            reference_call_location(
                path=origin.relative_path,
                text=origin.contents,
                start=starts[occurrence],
                call=invalid_call.call,
            )
            if origin is not None and occurrence < len(starts)
            else None
        )
        report_compile_diagnostic(
            key=reference_call_syntax_key(
                file_path=origin.file_path if origin is not None else None,
                call=invalid_call.call,
                location=location,
            ),
            diagnostic=CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.ERROR,
                code=REFERENCE_CALL_SYNTAX_CODE,
                message=invalid_call.message,
                resource_type=origin.resource_type if origin is not None else None,
                resource_name=origin.resource_name if origin is not None else None,
                path=origin.relative_path if origin is not None and location is None else None,
                location=location,
                help=invalid_call.help,
            ),
        )


def reference_call_syntax_key(
    *, file_path: Path | None, call: str, location: SourceLocation | None
) -> tuple[str, ...]:
    """Return the collector key shared by every report of one rejected reference call."""

    owner: str = file_path.as_posix() if file_path is not None else ""
    if location is None:
        return (REFERENCE_CALL_SYNTAX_CODE, owner, call)
    return (
        REFERENCE_CALL_SYNTAX_CODE,
        owner,
        f"{location.line:09d}:{location.column:09d}",
        call,
    )


def _authored_invalid_call_starts(
    *, origin: SqlReferenceOrigin | None, syntax: SqlLexicalSyntax
) -> dict[str, list[int]]:
    if origin is None:
        return {}
    authored: SqlReferenceScan | SqlReferenceScanFailure = _reference_scan_outcome(
        sql=origin.contents, syntax=syntax
    )
    if not isinstance(authored, SqlReferenceScan):
        return {}
    starts: dict[str, list[int]] = {}
    for invalid_call in authored.invalid_calls:
        starts.setdefault(invalid_call.call, []).append(invalid_call.start)
    return starts


def reference_call_location(*, path: Path, text: str, start: int, call: str) -> SourceLocation:
    """Return the span of ``call`` starting at ``start`` in ``text`` as a source location."""

    end: int = start + len(call)
    return SourceLocation(
        path=path,
        line=text.count("\n", 0, start) + 1,
        column=start - (text.rfind("\n", 0, start) + 1) + 1,
        end_line=text.count("\n", 0, end) + 1,
        end_column=end - (text.rfind("\n", 0, end) + 1) + 1,
    )
