"""Metadata-preserving MODEL and source declaration edits."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledModel, CompiledSource
from sqlbuild.compiler.contract_adoption.exceptions import ContractAdoptionError
from sqlbuild.compiler.contract_adoption.models import ContractFinding
from sqlbuild.compiler.contract_adoption.types import ContractFindingKind
from sqlbuild.compiler.discovery.main._model_header_spans import (
    get_model_header_spans,
)
from sqlbuild.compiler.discovery.models import ModelHeaderColumnSpan, ModelHeaderSpans
from sqlbuild.spec.contracts.models import SchemaColumn, SourceColumnEntry

_HEADER_WHITESPACE: str = " \t"
_GENERATED_MARKER: str = "generated"
_YAML_COLUMNS_KEY: str = "columns"
_YAML_TYPE_KEY: str = "type"
_YAML_KEY_SEPARATOR: str = ":"
_SINGLE_QUOTE: str = "'"
_DOUBLE_QUOTE: str = '"'
_MINIMUM_QUOTED_LENGTH: int = 2


def edit_model(
    *, model: CompiledModel, physical_columns: tuple[ColumnInfo, ...], overwrite: bool
) -> tuple[str | None, str | None]:
    if model.schema_entry is not None and model.schema_entry.model_schema is not None:
        return None, "model uses a shared SCHEMA declaration"
    if model.schema_entry is not None and any(
        column.location is not None and column.location.path != model.relative_path
        for column in model.schema_entry.columns
    ):
        return None, "effective columns are owned by an external schema file"
    contents: str = model.authored_sql
    header_spans: ModelHeaderSpans = get_model_header_spans(contents=contents)
    span_result: tuple[int, int, dict[str, ModelHeaderColumnSpan]] | None = header_spans.columns
    if span_result is None:
        header_span: tuple[int, int] | None = header_spans.body
        if header_span is None:
            return None, "MODEL header could not be edited safely"
        insertion: int = header_span[1]
        columns_sql: str = _render_model_columns(physical_columns)
        prefix: str = "\n  "
        return contents[:insertion] + prefix + columns_sql + contents[insertion:], None
    body_start, body_end, column_spans = span_result
    declared_by_name: dict[str, SchemaColumn] = {
        column.name.casefold(): column
        for column in (model.schema_entry.columns if model.schema_entry is not None else ())
    }
    physical_by_name: dict[str, ColumnInfo] = {
        column.name.casefold(): column for column in physical_columns
    }
    edits: list[tuple[int, int, str]] = []
    for name, declared in declared_by_name.items():
        column_span: ModelHeaderColumnSpan | None = column_spans.get(declared.name)
        if column_span is None:
            return None, f"column '{declared.name}' has no unambiguous authored span"
        physical: ColumnInfo | None = physical_by_name.get(name)
        if physical is None:
            if overwrite:
                edits.append((column_span.entry_start, column_span.entry_end, ""))
            continue
        if declared.type is None:
            metadata: str = contents[column_span.metadata_start : column_span.metadata_end]
            separator: str = ", " if metadata.strip() else ""
            edits.append(
                (
                    column_span.metadata_start,
                    column_span.metadata_start,
                    f"type {physical.type}{separator}",
                )
            )
        elif overwrite and declared.type.casefold() != physical.type.casefold():
            replacement_span: tuple[int, int] | None = _declared_type_span(
                contents=contents,
                column_span=column_span,
                declared_type=declared.type,
            )
            if replacement_span is None:
                return None, f"column '{declared.name}' type span could not be edited safely"
            edits.append((*replacement_span, physical.type))
    additions: tuple[ColumnInfo, ...] = tuple(
        column for column in physical_columns if column.name.casefold() not in declared_by_name
    )
    if additions:
        indentation: str = _column_indentation(contents=contents, body_start=body_start)
        rendered: str = "".join(
            f"\n{indentation}{column.name} (type {column.type})" for column in additions
        )
        edits.append((body_end, body_end, rendered + "\n  "))
    return _apply_text_edits(contents=contents, edits=edits), None


def _render_model_columns(columns: tuple[ColumnInfo, ...]) -> str:
    body: str = "".join(f"\n    {column.name} (type {column.type})" for column in columns)
    return f"columns ({body}\n  )"


def _column_indentation(*, contents: str, body_start: int) -> str:
    next_line: int = contents.find("\n", body_start)
    if next_line < 0:
        return "    "
    index: int = next_line + 1
    while index < len(contents) and contents[index] in _HEADER_WHITESPACE:
        index += 1
    return contents[next_line + 1 : index] or "    "


def _declared_type_span(
    *, contents: str, column_span: ModelHeaderColumnSpan, declared_type: str
) -> tuple[int, int] | None:
    metadata: str = contents[column_span.metadata_start : column_span.metadata_end]
    lowered: str = metadata.casefold()
    type_key: int = lowered.find("type")
    if type_key < 0:
        return None
    value_start: int = lowered.find(declared_type.casefold(), type_key + len("type"))
    if value_start < 0:
        return None
    absolute_start: int = column_span.metadata_start + value_start
    return absolute_start, absolute_start + len(declared_type)


def edit_source(
    *,
    source: CompiledSource,
    physical_columns: tuple[ColumnInfo, ...],
    overwrite: bool,
    contents: str | None = None,
) -> tuple[str | None, str | None]:
    contents = source.source_file.contents if contents is None else contents
    if _GENERATED_MARKER in "\n".join(source.source_file.contents.splitlines()[:5]).casefold():
        return None, "source file is marked as generated"
    lines: list[str] = contents.splitlines(keepends=True)
    source_range: tuple[int, int, int] | None = _yaml_named_block(
        lines=lines, name=source.name, minimum_indent=0
    )
    if source_range is None:
        return None, "source declaration has no unambiguous YAML block"
    source_start, source_end, source_indent = source_range
    columns_index: int | None = next(
        (
            index
            for index in range(source_start + 1, source_end)
            if _yaml_key(lines[index]) == _YAML_COLUMNS_KEY
            and _indent(lines[index]) == source_indent + 2
        ),
        None,
    )
    declared_by_name: dict[str, SourceColumnEntry] = {
        column.name.casefold(): column for column in source.source_entry.columns
    }
    physical_by_name: dict[str, ColumnInfo] = {
        column.name.casefold(): column for column in physical_columns
    }
    if columns_index is None:
        insertion_lines: list[str] = [" " * (source_indent + 2) + "columns:\n"]
        for column in physical_columns:
            insertion_lines.extend(_yaml_column_lines(column=column, indent=source_indent + 4))
        lines[source_end:source_end] = insertion_lines
        return "".join(lines), None
    columns_end: int = columns_index + 1
    while columns_end < source_end:
        stripped: str = lines[columns_end].strip()
        if (
            stripped
            and not stripped.startswith("#")
            and _indent(lines[columns_end]) <= source_indent + 2
        ):
            break
        columns_end += 1
    column_indent: int = source_indent + 4
    column_blocks: dict[str, tuple[int, int]] = {}
    index: int = columns_index + 1
    while index < columns_end:
        parsed_name: str | None = _yaml_list_name(lines[index])
        if parsed_name is not None and _indent(lines[index]) == column_indent:
            block_end: int = index + 1
            while block_end < columns_end and not (
                _indent(lines[block_end]) <= column_indent
                and _yaml_list_name(lines[block_end]) is not None
            ):
                block_end += 1
            column_blocks[parsed_name.casefold()] = (index, block_end)
            index = block_end
            continue
        index += 1
    line_edits: list[tuple[int, int, list[str]]] = []
    for name, declared in declared_by_name.items():
        block: tuple[int, int] | None = column_blocks.get(name)
        if block is None:
            return None, f"source column '{declared.name}' has no unambiguous YAML block"
        physical: ColumnInfo | None = physical_by_name.get(name)
        if physical is None:
            if overwrite:
                line_edits.append((block[0], block[1], []))
            continue
        type_line: int | None = next(
            (i for i in range(block[0] + 1, block[1]) if _yaml_key(lines[i]) == _YAML_TYPE_KEY),
            None,
        )
        if type_line is None:
            line_edits.append(
                (
                    block[0] + 1,
                    block[0] + 1,
                    [" " * (column_indent + 2) + f"type: {_yaml_string(physical.type)}\n"],
                )
            )
        elif (
            overwrite
            and declared.type is not None
            and declared.type.casefold() != physical.type.casefold()
        ):
            newline: str = "\n" if lines[type_line].endswith("\n") else ""
            comment: str = _yaml_comment(lines[type_line])
            line_edits.append(
                (
                    type_line,
                    type_line + 1,
                    [
                        " " * (column_indent + 2)
                        + f"type: {_yaml_string(physical.type)}"
                        + comment
                        + newline
                    ],
                )
            )
    additions: tuple[ColumnInfo, ...] = tuple(
        column for column in physical_columns if column.name.casefold() not in declared_by_name
    )
    if additions:
        insertion: list[str] = []
        for column in additions:
            insertion.extend(_yaml_column_lines(column=column, indent=column_indent))
        line_edits.append((columns_end, columns_end, insertion))
    for start, end, replacement_lines in sorted(line_edits, reverse=True):
        lines[start:end] = replacement_lines
    return "".join(lines), None


def _yaml_named_block(
    *, lines: list[str], name: str, minimum_indent: int
) -> tuple[int, int, int] | None:
    matches: list[tuple[int, int]] = [
        (index, _indent(line))
        for index, line in enumerate(lines)
        if _yaml_list_name(line) == name and _indent(line) >= minimum_indent
    ]
    if not matches:
        return None
    minimum: int = min(indent for _, indent in matches)
    candidates: list[int] = [index for index, indent in matches if indent == minimum]
    if len(candidates) != 1:
        return None
    start: int = candidates[0]
    end: int = start + 1
    while end < len(lines):
        if _indent(lines[end]) <= minimum and _yaml_list_name(lines[end]) is not None:
            break
        end += 1
    return start, end, minimum


def _yaml_list_name(line: str) -> str | None:
    stripped: str = line.strip()
    if not stripped.startswith("- name:"):
        return None
    return _unquote(stripped[len("- name:") :].strip())


def _yaml_key(line: str) -> str | None:
    stripped: str = line.strip()
    if not stripped or stripped.startswith(("#", "-")) or _YAML_KEY_SEPARATOR not in stripped:
        return None
    return stripped.split(_YAML_KEY_SEPARATOR, maxsplit=1)[0].strip()


def _yaml_comment(line: str) -> str:
    marker: int = line.find(" #")
    if marker < 0:
        return ""
    return line[marker:].rstrip("\n")


def _yaml_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _unquote(value: str) -> str:
    if (
        len(value) >= _MINIMUM_QUOTED_LENGTH
        and value[0] == value[-1]
        and value[0] in {_SINGLE_QUOTE, _DOUBLE_QUOTE}
    ):
        return value[1:-1]
    return value


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _yaml_column_lines(*, column: ColumnInfo, indent: int) -> list[str]:
    return [
        " " * indent + f"- name: {column.name}\n",
        " " * (indent + 2) + f"type: {_yaml_string(column.type)}\n",
    ]


def _apply_text_edits(*, contents: str, edits: list[tuple[int, int, str]]) -> str:
    result: str = contents
    previous_start: int = len(contents) + 1
    for start, end, replacement_text in sorted(edits, reverse=True):
        if end > previous_start:
            raise ContractAdoptionError("overlapping contract source edits")
        result = result[:start] + replacement_text + result[end:]
        previous_start = start
    return result


def remaining_findings(
    *, findings: tuple[ContractFinding, ...], overwrite: bool, conflict: str | None
) -> tuple[ContractFinding, ...]:
    if conflict is not None:
        first: ContractFinding | None = findings[0] if findings else None
        if first is None:
            raise ContractAdoptionError("contract ownership conflict requires resource evidence")
        return (
            *findings,
            ContractFinding(
                resource_type=first.resource_type,
                resource_name=first.resource_name,
                kind=ContractFindingKind.OWNERSHIP_CONFLICT,
                message=conflict,
            ),
        )
    resolved: set[ContractFindingKind] = {ContractFindingKind.MISSING_DECLARATION}
    if overwrite:
        resolved.update(
            {ContractFindingKind.TYPE_MISMATCH, ContractFindingKind.MISSING_PHYSICAL_COLUMN}
        )
    return tuple(finding for finding in findings if finding.kind not in resolved)
