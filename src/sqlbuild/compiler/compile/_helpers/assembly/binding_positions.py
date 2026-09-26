"""Construct authored locations from native normalization and expansion maps."""

from functools import lru_cache
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledSqlExpansion, CompileModelInput, ExpansionSpan
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic
from sqlbuild.compiler.sql_analysis.types import NativeBindingPositions, NativePositionsModule
from sqlbuild.spec.contracts.models import SourceLocation


def query_line_offset(model_input: CompileModelInput) -> int | None:
    query_sql: str = model_input.model_file.query_sql
    query_start: int = model_input.model_file.contents.find(query_sql)
    if query_start < 0:
        return None
    return model_input.model_file.contents[:query_start].count("\n")


@lru_cache(maxsize=32)
def _mapper(
    *,
    authored_sql: str,
    authored_query_sql: str,
    expanded_sql: str,
    cleaned_sql: str,
    passes: tuple[tuple[ExpansionSpan, ...], ...],
) -> NativeBindingPositions:
    native_passes: list[tuple[tuple[int, int, int, int], ...]] = []
    for spans in passes:
        native_passes.append(
            tuple(
                (span.source_start, span.source_end, span.output_start, span.output_end)
                for span in spans
            )
        )
    return cast(NativePositionsModule, _native).BindingPositions(
        {
            "authored": authored_sql,
            "query": authored_query_sql,
            "expanded": expanded_sql,
            "cleaned": cleaned_sql,
            "passes": native_passes,
        }
    )


def get_authored_binding_location(
    *,
    path: Path,
    authored_sql: str,
    authored_query_sql: str,
    cleaned_sql: str,
    diagnostic: SqlBindingDiagnostic,
    expansion: CompiledSqlExpansion | None = None,
) -> SourceLocation | None:
    mapper: NativeBindingPositions = _mapper(
        authored_sql=authored_sql,
        authored_query_sql=authored_query_sql,
        expanded_sql=expansion.expanded_sql if expansion is not None else authored_query_sql,
        cleaned_sql=cleaned_sql,
        passes=expansion.passes if expansion is not None else (),
    )
    line, column = mapper.position(
        start=diagnostic.start,
        line=diagnostic.line,
        column=diagnostic.column,
        message=diagnostic.message,
    )
    if line is None or column is None:
        return None
    end_line: int | None = None
    end_column: int | None = None
    if diagnostic.end is not None:
        end_line, end_column = mapper.position(
            start=diagnostic.end, line=None, column=None, message=""
        )
    return SourceLocation(
        path=path, line=line, column=column, end_line=end_line, end_column=end_column
    )


def get_authored_binding_position(
    *,
    authored_sql: str,
    authored_query_sql: str,
    cleaned_sql: str,
    diagnostic: SqlBindingDiagnostic,
    expansion: CompiledSqlExpansion | None = None,
) -> tuple[int | None, int | None]:
    mapper: NativeBindingPositions = _mapper(
        authored_sql=authored_sql,
        authored_query_sql=authored_query_sql,
        expanded_sql=expansion.expanded_sql if expansion is not None else authored_query_sql,
        cleaned_sql=cleaned_sql,
        passes=expansion.passes if expansion is not None else (),
    )
    return mapper.position(
        start=diagnostic.start,
        line=diagnostic.line,
        column=diagnostic.column,
        message=diagnostic.message,
    )
