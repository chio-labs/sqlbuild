"""Propagate unknown output types from located root errors without opening other columns."""

from collections import Counter, deque
from dataclasses import replace
from typing import Any

from sqlbuild.compiler.compile._helpers.analysis.compact import get_complete_schema_binding_request
from sqlbuild.compiler.compile._helpers.assembly.native_declarations import (
    known_declared_types,
    known_function_names,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import semantic_shapes
from sqlbuild.compiler.compile._helpers.diagnostics.details import update_binding_models
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompilerDiagnostic,
    InferredColumn,
)
from sqlbuild.compiler.sql_analysis.main._identifier_case import ignores_quoted_case
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingDiagnostic,
    SqlBindingResult,
    SqlSchemaValidationRequest,
)

_SELECT: str = "SELECT"
_PROJECTION_END: frozenset[str] = frozenset(
    {
        "FROM",
        "WHERE",
        "GROUP_BY",
        "HAVING",
        "QUALIFY",
        "ORDER_BY",
        "LIMIT",
        "UNION",
        "INTERSECT",
        "EXCEPT",
    }
)
_OPEN: str = "("
_CLOSE: str = ")"
_COMMA: str = ","


def recover_output_types(
    *, project: CompiledProject, binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]]
) -> CompiledProject:
    """Recheck only failed dependants using unknown types for poisoned lineage outputs."""
    failed: list[CompiledModel] = [model for model in project.models if model.binding_diagnostics]
    blocking: list[CompilerDiagnostic] = []
    for model in failed:
        blocking.extend(item for item in model.binding_diagnostics if item.is_error)
    if not blocking:
        return project
    shapes: dict[str, dict[str, str]] = semantic_shapes(project=project)
    requests: tuple[SqlSchemaValidationRequest, ...] = tuple(
        _request(project=project, model=model, shapes=shapes) for model in failed
    )
    results: tuple[SqlBindingResult, ...] = tuple(
        SqlBindingResult(diagnostics=binding_results.get(model.name, ())) for model in failed
    )
    poisoned: dict[tuple[str, str], CompilerDiagnostic] = {}
    roots_by_model: dict[str, dict[SqlBindingDiagnostic, CompilerDiagnostic]] = {}
    outputs_by_diagnostic: dict[CompilerDiagnostic, set[str]] = {}
    for model, request, result in zip(failed, requests, results, strict=True):
        roots_by_model[model.name] = _root_bindings(model=model, diagnostics=result.diagnostics)
        spans: list[tuple[int, int]] = _projection_spans(sql=request.sql, dialect=request.dialect)
        columns: tuple[InferredColumn, ...] = model.inferred_columns or ()
        if len(spans) != len(columns):
            continue
        for raw in result.diagnostics:
            if raw.start is None:
                continue
            root: CompilerDiagnostic | None = roots_by_model[model.name].get(raw)
            if root is None or not root.is_error:
                continue
            for column, (start, end) in zip(columns, spans, strict=True):
                if start <= raw.start < end:
                    poisoned[(model.name, column.name)] = root
                    outputs_by_diagnostic.setdefault(root, set()).add(column.name)
    if not poisoned:
        return project
    for _ in project.models:
        previous: int = len(poisoned)
        for model in project.models:
            for output in model.fast_lineage_columns or ():
                for source in output.upstream_columns:
                    root = poisoned.get((source.resource_name, source.column_name))
                    if root is not None:
                        poisoned.setdefault((model.name, output.output_column), root)
        if len(poisoned) == previous:
            break
    unknown_shapes: dict[str, dict[str, str]] = {
        name: dict(columns) for name, columns in shapes.items()
    }
    for name, column_name in poisoned:
        if name in unknown_shapes and column_name in unknown_shapes[name]:
            unknown_shapes[name][column_name] = "UNKNOWN"
    skipped: set[CompilerDiagnostic] = set()
    redirected: dict[CompilerDiagnostic, set[CompilerDiagnostic]] = {}
    for model, original in zip(failed, results, strict=True):
        causes: set[CompilerDiagnostic] = set()
        for reference in model.references:
            causes.update(
                root for (name, _), root in poisoned.items() if name == reference.ref_name
            )
        if not causes:
            continue
        revised: SqlBindingResult = get_schema_validations(
            requests=(_request(project=project, model=model, shapes=unknown_shapes),)
        )[0]
        remaining: set[tuple[str, int | None, int | None]] = {
            (item.code, item.start, item.end) for item in revised.diagnostics
        }
        for raw in original.diagnostics:
            diagnostic: CompilerDiagnostic | None = roots_by_model[model.name].get(raw)
            if (
                diagnostic is None
                or diagnostic in causes
                or (raw.code, raw.start, raw.end) in remaining
            ):
                continue
            skipped.add(diagnostic)
            redirected[diagnostic] = (
                _output_causes(
                    model=model,
                    outputs=outputs_by_diagnostic.get(diagnostic, set()),
                    poisoned=poisoned,
                )
                or causes
            )
    counts: Counter[CompilerDiagnostic] = _unchecked_uses(
        project=project, poisoned=poisoned, redirected=redirected
    )
    diagnostics: tuple[CompilerDiagnostic, ...] = tuple(
        replace(
            item,
            notes=(
                *item.notes,
                *(
                    (
                        f"{counts[item]} downstream output uses were not type-checked "
                        "because of this error",
                    )
                    if counts[item]
                    else ()
                ),
            ),
        )
        for item in project.diagnostics
        if item not in skipped
    )
    models: list[CompiledModel] = []
    for model in update_binding_models(models=project.models, diagnostics=diagnostics):
        updated: tuple[InferredColumn, ...] | None = None
        if model.inferred_columns is not None:
            updated = tuple(
                replace(column, type=None) if (model.name, column.name) in poisoned else column
                for column in model.inferred_columns
            )
        models.append(
            replace(
                model,
                inferred_columns=updated,
                unchecked_output_columns=frozenset(
                    column for name, column in poisoned if name == model.name
                ),
            )
        )
    return replace(project, models=tuple(models), diagnostics=diagnostics)


def _unchecked_uses(
    *,
    project: CompiledProject,
    poisoned: dict[tuple[str, str], CompilerDiagnostic],
    redirected: dict[CompilerDiagnostic, set[CompilerDiagnostic]],
) -> Counter[CompilerDiagnostic]:
    """Attribute transitive unchecked output uses to retained root errors."""
    counts: Counter[CompilerDiagnostic] = Counter()
    for model in project.models:
        for output in model.fast_lineage_columns or ():
            pending: list[CompilerDiagnostic] = []
            for source in output.upstream_columns:
                root: CompilerDiagnostic | None = poisoned.get(
                    (source.resource_name, source.column_name)
                )
                if root is not None:
                    pending.append(root)
            visited: set[CompilerDiagnostic] = set()
            while pending:
                root = pending.pop()
                if root in visited:
                    continue
                visited.add(root)
                if root in redirected:
                    pending.extend(redirected[root])
                else:
                    counts[root] += 1
    return counts


def _root_bindings(
    *, model: CompiledModel, diagnostics: tuple[SqlBindingDiagnostic, ...]
) -> dict[SqlBindingDiagnostic, CompilerDiagnostic]:
    """Pair repeated messages by occurrence, preserving distinct native spans."""
    pending: dict[tuple[str, str], deque[CompilerDiagnostic]] = {}
    for diagnostic in model.binding_diagnostics:
        pending.setdefault((diagnostic.code, diagnostic.message), deque()).append(diagnostic)
    result: dict[SqlBindingDiagnostic, CompilerDiagnostic] = {}
    for raw in diagnostics:
        matches: deque[CompilerDiagnostic] | None = pending.get((raw.code, raw.message))
        if matches:
            result[raw] = matches.popleft()
    return result


def _output_causes(
    *, model: CompiledModel, outputs: set[str], poisoned: dict[tuple[str, str], CompilerDiagnostic]
) -> set[CompilerDiagnostic]:
    """Redirect only the failing projection's lineage instead of every poisoned input."""
    result: set[CompilerDiagnostic] = set()
    for output in model.fast_lineage_columns or ():
        if output.output_column in outputs:
            for source in output.upstream_columns:
                root: CompilerDiagnostic | None = poisoned.get(
                    (source.resource_name, source.column_name)
                )
                if root is not None:
                    result.add(root)
    return result


def _request(
    *, project: CompiledProject, model: CompiledModel, shapes: dict[str, dict[str, str]]
) -> SqlSchemaValidationRequest:
    return replace(
        get_complete_schema_binding_request(
            query_sql=model.query_sql,
            placeholders=None,
            dialect=project.sql_analysis_dialect,
            known_functions=known_function_names(project.functions),
            known_types=known_declared_types(functions=project.functions, column_types=shapes),
            binding_schema={
                reference.ref_name: shapes.get(reference.ref_name, {})
                for reference in model.references
            },
        ),
        catalog=project.binding_catalog,
        quoted_identifiers_ignore_case=ignores_quoted_case(
            connection=project.effective_connection, dialect=project.sql_analysis_dialect
        ),
    )


def _projection_spans(*, sql: str, dialect: str | None) -> list[tuple[int, int]]:
    module: Any = import_polyglot_sql()
    tokens: list[dict[str, Any]] = module.tokenize(sql, dialect=dialect)
    depth: int = 0
    start: int | None = None
    spans: list[tuple[int, int]] = []
    for token in tokens:
        text: str = token["text"]
        if text == _OPEN:
            depth += 1
        elif text == _CLOSE:
            depth -= 1
        elif depth == 0:
            if start is None and token["token_type"] == _SELECT:
                start = token["span"]["end"]
            elif start is not None and token["token_type"] in _PROJECTION_END:
                spans.append((start, token["span"]["start"]))
                return spans
            elif start is not None and text == _COMMA:
                spans.append((start, token["span"]["start"]))
                start = token["span"]["end"]
    if start is not None:
        spans.append((start, len(sql)))
    return spans
