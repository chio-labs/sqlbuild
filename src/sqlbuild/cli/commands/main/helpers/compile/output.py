"""Compile command output formatting."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.compile.models import WrittenTarget
from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.compiler.compile.models.core import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
)
from sqlbuild.compiler.compile.models.sql_tests import (
    CompiledModelSqlTestPayload,
    CompiledSqlTest,
)
from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic, RelatedLocation
from sqlbuild.compiler.diagnostics.types import DiagnosticSeverity
from sqlbuild.compiler.lineage.models import ModelColumnLineage, ProjectColumnLineage
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry
from sqlbuild.spec.models.schema import SourceLocation

_HUMAN_MODEL_LIMIT: int = 100
_MIN_MODEL_NAME_WIDTH: int = 24
_MAX_MODEL_NAME_WIDTH: int = 48


def format_compile_text(
    *,
    graph: ProjectGraph,
    written: WrittenTarget,
    manifest: bool,
    lineage: ProjectColumnLineage | None,
    diagnostics: tuple[CompilerDiagnostic, ...],
    lineage_mode: CompileLineageMode = CompileLineageMode.FAST,
    use_color: bool,
) -> str:
    """Format human-readable compile output."""

    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [
        style.success_strong(f"Compile ready ({_count_label(len(graph.project.models), 'model')})"),
        "",
    ]
    visible_models: tuple[CompiledModel, ...] = graph.project.models[:_HUMAN_MODEL_LIMIT]
    model_name_width: int = _model_name_width(visible_models)
    error_models: frozenset[str] = _models_with_error_diagnostics(diagnostics)
    for model in visible_models:
        model_name: str = _fit(model.name, width=model_name_width)
        status: str = "FAIL" if model.name in error_models else "OK"
        lines.append(
            f"  {style.object_name(model_name)} "
            f"{style.status(status)} "
            f"{style.muted(f'{_column_count(model)} columns')}"
        )
    hidden_model_count: int = len(graph.project.models) - len(visible_models)
    if hidden_model_count > 0:
        lines.append("")
        lines.append(
            "  "
            + style.muted(f"Showing {len(visible_models)} of {len(graph.project.models)} models.")
        )
        lines.append("  " + style.muted("Use --json for the full compile report."))
    lines.append("")
    if diagnostics:
        lines.append(
            _format_diagnostics_text(
                diagnostics,
                source_texts=_model_source_texts(graph.project.models),
                style=style,
            )
        )
        lines.append("")
    error_count: int = _diagnostic_count(diagnostics, DiagnosticSeverity.ERROR)
    warning_count: int = _diagnostic_count(diagnostics, DiagnosticSeverity.WARNING)
    lines.append(
        f"  {style.success_strong('Compiled:')} "
        f"{_count_label(len(graph.project.models), 'model')}, "
        f"{_count_label(len(graph.project.seeds), 'seed')}, "
        f"{_count_label(len(graph.project.functions), 'function')}, "
        f"{_count_label(error_count, 'error')}, "
        f"{_count_label(warning_count, 'warning')}"
    )
    lines.append(f"  {style.muted('Wrote:')} {_relative_target_path(_compiled_sql_dir(written))}/")
    if manifest:
        lines.append(f"  {style.muted('Wrote:')} target/manifest.json")
    if (
        lineage is None
        and graph.project.settings.sqlglot
        and lineage_mode != CompileLineageMode.NONE
    ):
        lines.append(f"  {style.warning('Column lineage:')} unavailable")
    return "\n" + "\n".join(lines) + "\n"


def format_compile_json(
    *,
    graph: ProjectGraph,
    written: WrittenTarget,
    manifest: bool,
    timings_ms: dict[str, int],
    lineage: ProjectColumnLineage | None,
    diagnostics: tuple[CompilerDiagnostic, ...],
    lineage_mode: CompileLineageMode = CompileLineageMode.FAST,
) -> str:
    """Serialize the offline compile report as JSON."""

    result: dict[str, object] = {
        "version": _sqlbuild_version(),
        "command": "compile",
        "offline": True,
        "has_errors": any(diagnostic.is_error for diagnostic in diagnostics),
        "summary": _summary(graph, diagnostics=diagnostics),
        "diagnostics": [_diagnostic_to_json(diagnostic) for diagnostic in diagnostics],
        "compile_timings": timings_ms,
        "lineage_mode": lineage_mode.value,
        "resources": _resources(graph=graph, lineage=lineage),
        "artifacts": _artifacts(written=written, manifest=manifest),
    }
    return json.dumps(result, indent=2)


def _summary(graph: ProjectGraph, *, diagnostics: tuple[CompilerDiagnostic, ...]) -> dict[str, int]:
    project: CompiledProject = graph.project
    return {
        "models": len(project.models),
        "selected_models": len(project.models),
        "sources": len(project.sources),
        "seeds": len(project.seeds),
        "functions": len(project.functions),
        "audits": len(project.audits),
        "tests": len(project.sql_tests),
        "execution_layers": _execution_layer_count(graph),
        "errors": _diagnostic_count(diagnostics, DiagnosticSeverity.ERROR),
        "warnings": _diagnostic_count(diagnostics, DiagnosticSeverity.WARNING),
    }


def _resources(*, graph: ProjectGraph, lineage: ProjectColumnLineage | None) -> dict[str, object]:
    project: CompiledProject = graph.project
    return {
        "models": [
            _model_resource(graph=graph, model=model, lineage=lineage) for model in project.models
        ],
        "sources": [_source_resource(source) for source in project.sources],
        "seeds": [_seed_resource(seed) for seed in project.seeds],
        "functions": [_function_resource(function) for function in project.functions],
        "audits": [_audit_resource(audit) for audit in project.audits],
        "tests": [_test_resource(test) for test in project.sql_tests],
    }


def _model_resource(
    *,
    graph: ProjectGraph,
    model: CompiledModel,
    lineage: ProjectColumnLineage | None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "name": model.name,
        "relative_path": str(model.relative_path),
        "materialized": str(model.config.values.get("materialized", "view")),
        "column_count": _column_count(model),
        "depends_on": [_serialize_key(dep) for dep in graph.upstream_deps.get(model.key, ())],
        "lineage": _lineage_summary(lineage=lineage, model=model),
        "query_sql": model.query_sql,
    }
    if model.destination.qualified_name is not None:
        item["qualified_name"] = model.destination.qualified_name
    for hook_key in ("pre_hooks", "post_hooks"):
        hooks: object = model.config.values.get(hook_key)
        if hooks is not None:
            item[hook_key] = _hook_resources(hooks=hooks)
    return item


def _hook_resources(*, hooks: object) -> list[dict[str, object]]:
    if not isinstance(hooks, (list, tuple)):
        return []
    resources: list[dict[str, object]] = []
    hook: object
    for hook in hooks:
        if isinstance(hook, SqlHookEntry):
            resources.append({"type": "sql", "statement": hook.statement})
        elif isinstance(hook, PythonHookEntry):
            resources.append({"type": "python", "name": hook.name, "kwargs": hook.kwargs})
    return resources


def _source_resource(source: CompiledSource) -> dict[str, object]:
    return {
        "name": source.name,
        "relative_path": str(source.source_file.relative_path),
        "column_count": len(source.source_entry.columns),
    }


def _seed_resource(seed: CompiledSeed) -> dict[str, object]:
    item: dict[str, object] = {
        "name": seed.name,
        "relative_path": str(seed.seed_file.relative_path),
        "column_count": len(seed.schema_entry.columns),
    }
    if seed.destination.qualified_name is not None:
        item["qualified_name"] = seed.destination.qualified_name
    return item


def _function_resource(function: CompiledFunction) -> dict[str, object]:
    item: dict[str, object] = {
        "name": function.name,
        "relative_path": str(function.relative_path),
        "language": function.language.value,
        "return_kind": "table" if function.return_columns else "scalar",
        "returns": function.returns,
        "return_columns": [
            {"name": column.name, "type": column.type} for column in function.return_columns
        ],
    }
    if function.destination.qualified_name is not None:
        item["qualified_name"] = function.destination.qualified_name
    return item


def _audit_resource(audit: CompiledAudit) -> dict[str, object]:
    item: dict[str, object] = {
        "name": audit.name,
        "relative_path": str(audit.audit_file.relative_path),
    }
    if audit.attached_target_kind is not None and audit.attached_target_name is not None:
        item["attached_to"] = {
            "resource_type": audit.attached_target_kind.value,
            "name": audit.attached_target_name,
        }
        if audit.attached_column_name is not None:
            item["attached_to"]["column_name"] = audit.attached_column_name
    return item


def _test_resource(test: CompiledSqlTest) -> dict[str, object]:
    expected_models: list[str] = []
    if isinstance(test.payload, CompiledModelSqlTestPayload):
        expected_models = list(test.payload.expected_model_names)
    return {
        "name": test.name,
        "relative_path": str(test.test_file.relative_path),
        "expected_models": expected_models,
    }


def _lineage_summary(
    *, lineage: ProjectColumnLineage | None, model: CompiledModel
) -> dict[str, object]:
    if lineage is None:
        return {"available": False}
    model_lineage: ModelColumnLineage | None = lineage.models.get(model.name)
    if model_lineage is None:
        return {"available": False}
    return {
        "available": True,
        "column_count": _column_count(model),
        "edge_count": len(lineage.edges_targeting(model.name)),
        "has_star": model_lineage.has_star,
    }


def _artifacts(*, written: WrittenTarget, manifest: bool) -> dict[str, object]:
    return {
        "compiled_sql_dir": _relative_target_path(_compiled_sql_dir(written)) + "/",
        "manifest": "target/manifest.json" if manifest else None,
    }


def _column_count(model: CompiledModel) -> int:
    if model.inferred_columns is not None:
        return len(model.inferred_columns)
    if model.schema_entry is not None:
        return len(model.schema_entry.columns)
    return 0


def _model_name_width(models: tuple[CompiledModel, ...]) -> int:
    longest: int = max((len(model.name) for model in models), default=0)
    return min(max(longest, _MIN_MODEL_NAME_WIDTH), _MAX_MODEL_NAME_WIDTH)


def _fit(text: str, *, width: int) -> str:
    if len(text) > width:
        if width <= 3:
            return "." * width
        return text[: width - 3] + "..."
    return text.ljust(width)


def _count_label(count: int, singular: str) -> str:
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {singular}s"


def _diagnostic_count(
    diagnostics: tuple[CompilerDiagnostic, ...], severity: DiagnosticSeverity
) -> int:
    return sum(1 for diagnostic in diagnostics if diagnostic.severity == severity)


def _models_with_error_diagnostics(
    diagnostics: tuple[CompilerDiagnostic, ...],
) -> frozenset[str]:
    return frozenset(
        diagnostic.resource_name
        for diagnostic in diagnostics
        if diagnostic.is_error and diagnostic.resource_name is not None
    )


def _diagnostic_to_json(diagnostic: CompilerDiagnostic) -> dict[str, object]:
    payload: dict[str, object] = {
        "phase": str(diagnostic.phase),
        "severity": str(diagnostic.severity),
        "code": diagnostic.code,
        "message": diagnostic.message,
    }
    if diagnostic.resource_type is not None:
        payload["resource_type"] = str(diagnostic.resource_type)
    if diagnostic.resource_name is not None:
        payload["resource_name"] = diagnostic.resource_name
    if diagnostic.column_name is not None:
        payload["column_name"] = diagnostic.column_name
    if diagnostic.path is not None:
        payload["path"] = str(diagnostic.path)
    if diagnostic.line is not None:
        payload["line"] = diagnostic.line
    if diagnostic.column is not None:
        payload["column"] = diagnostic.column
    if diagnostic.location is not None:
        payload["location"] = _location_to_json(diagnostic.location)
    if diagnostic.related_locations:
        payload["related_locations"] = [
            {
                "label": related.label,
                "location": _location_to_json(related.location),
                **({"message": related.message} if related.message is not None else {}),
            }
            for related in diagnostic.related_locations
        ]
    if diagnostic.help is not None:
        payload["help"] = diagnostic.help
    return payload


def _location_to_json(location: SourceLocation) -> dict[str, object]:
    payload: dict[str, object] = {
        "path": str(location.path),
        "line": location.line,
        "column": location.column,
    }
    if location.end_line is not None:
        payload["end_line"] = location.end_line
    if location.end_column is not None:
        payload["end_column"] = location.end_column
    return payload


def _format_diagnostics_text(
    diagnostics: tuple[CompilerDiagnostic, ...], *, source_texts: dict[Path, str], style: CliStyle
) -> str:
    lines: list[str] = []
    for diagnostic in diagnostics:
        lines.extend(
            _format_diagnostic_text(
                diagnostic,
                source_texts=source_texts,
                style=style,
            )
        )
        lines.append("")
    if lines:
        lines.pop()
    return "\n".join(lines)


def _format_diagnostic_text(
    diagnostic: CompilerDiagnostic, *, source_texts: dict[Path, str], style: CliStyle
) -> list[str]:
    header: str = f"{diagnostic.severity}[{diagnostic.code}]: {diagnostic.message}"
    lines: list[str] = [_style_diagnostic(header, diagnostic, style=style)]
    if diagnostic.resource_name is not None:
        label: str = "model"
        resource: str = diagnostic.resource_name
        if diagnostic.resource_type is not None and str(diagnostic.resource_type) != "model":
            label = "resource"
            resource = f"{diagnostic.resource_type}: {resource}"
        lines.append(f"  {label}: {style.object_name(resource)}")
    if diagnostic.location is not None:
        lines.extend(
            _format_location_block(
                diagnostic.location,
                source_texts=source_texts,
                message=None,
            )
        )
    elif diagnostic.path is not None:
        lines.append(f"  --> {diagnostic.path}")
    for related_location in diagnostic.related_locations:
        lines.append("")
        lines.append(f"  {related_location.label}:")
        lines.extend(
            _format_related_location_block(
                related_location,
                source_texts=source_texts,
            )
        )
    if diagnostic.help is not None:
        lines.append(f"  {style.muted('= help:')} {diagnostic.help}")
    return lines


def _format_related_location_block(
    related_location: RelatedLocation, *, source_texts: dict[Path, str]
) -> list[str]:
    return _format_location_block(
        related_location.location,
        source_texts=source_texts,
        message=related_location.message,
    )


def _format_location_block(
    location: SourceLocation, *, source_texts: dict[Path, str], message: str | None
) -> list[str]:
    rendered_location: str = f"{location.path}:{location.line}:{location.column}"
    lines: list[str] = [f"  --> {rendered_location}"]
    source_text: str | None = source_texts.get(location.path)
    if source_text is None:
        return lines
    source_lines: list[str] = source_text.splitlines()
    if location.line < 1 or location.line > len(source_lines):
        return lines
    source_line: str = source_lines[location.line - 1]
    line_number: str = str(location.line)
    gutter: str = " " * len(line_number)
    lines.append(f"  {gutter} |")
    lines.append(f"  {line_number} | {source_line}")
    lines.append(
        f"  {gutter} | {_caret_line(location=location, source_line=source_line, message=message)}"
    )
    return lines


def _caret_line(*, location: SourceLocation, source_line: str, message: str | None) -> str:
    start_column: int = max(1, location.column)
    end_column: int = location.end_column or start_column + 1
    if location.end_line is not None and location.end_line != location.line:
        end_column = len(source_line) + 1
    caret_count: int = max(1, end_column - start_column)
    suffix: str = f" {message}" if message is not None else ""
    return " " * (start_column - 1) + "^" * caret_count + suffix


def _model_source_texts(models: tuple[CompiledModel, ...]) -> dict[Path, str]:
    return {model.relative_path: model.authored_sql for model in models if model.authored_sql}


def _style_diagnostic(text: str, diagnostic: CompilerDiagnostic, *, style: CliStyle) -> str:
    if diagnostic.severity == DiagnosticSeverity.ERROR:
        return style.error(text)
    if diagnostic.severity == DiagnosticSeverity.WARNING:
        return style.warning(text)
    return style.muted(text)


def _serialize_key(key: CompiledObjectKey) -> dict[str, str]:
    return {"resource_type": str(key.resource_type), "name": key.name}


def _execution_layer_count(graph: ProjectGraph) -> int:
    model_keys: set[CompiledObjectKey] = {model.key for model in graph.project.models}
    if not model_keys:
        return 0
    remaining_model_deps: dict[CompiledObjectKey, set[CompiledObjectKey]] = {
        key: {dep for dep in graph.upstream_deps.get(key, ()) if dep in model_keys}
        for key in model_keys
    }
    downstream_model_deps: dict[CompiledObjectKey, set[CompiledObjectKey]] = {
        key: {dep for dep in graph.downstream_deps.get(key, ()) if dep in model_keys}
        for key in model_keys
    }
    current_layer: set[CompiledObjectKey] = {
        key for key, deps in remaining_model_deps.items() if not deps
    }
    visited: set[CompiledObjectKey] = set()
    layer_count: int = 0
    while current_layer:
        layer_count += 1
        next_layer: set[CompiledObjectKey] = set()
        for key in current_layer:
            visited.add(key)
            for downstream_key in downstream_model_deps.get(key, set()):
                if downstream_key in visited:
                    continue
                remaining_model_deps[downstream_key].discard(key)
                if not remaining_model_deps[downstream_key]:
                    next_layer.add(downstream_key)
        current_layer = next_layer
    if len(visited) != len(model_keys):
        return max(layer_count, 1)
    return layer_count


def _relative_target_path(path: Path) -> str:
    parts: tuple[str, ...] = path.parts
    if "target" in parts:
        target_index: int = parts.index("target")
        return Path(*parts[target_index:]).as_posix()
    return path.as_posix()


def _compiled_sql_dir(written: WrittenTarget) -> Path:
    return written.target_dir / "compiled"


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "unknown"
