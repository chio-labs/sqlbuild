"""Compile command output formatting."""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.compile.models import WrittenTarget
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
    CompiledSqlTest,
)
from sqlbuild.compiler.lineage.models import ModelColumnLineage, ProjectColumnLineage
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.shared.helpers.colors import blue_bold, dim, green, green_bold, yellow

_HUMAN_MODEL_LIMIT: int = 100
_MIN_MODEL_NAME_WIDTH: int = 24
_MAX_MODEL_NAME_WIDTH: int = 48


def format_compile_text(
    *,
    graph: ProjectGraph,
    written: WrittenTarget,
    manifest: bool,
    lineage: ProjectColumnLineage | None,
    use_color: bool,
) -> str:
    """Format human-readable compile output."""

    lines: list[str] = [
        _style(
            f"Compile ready ({_count_label(len(graph.project.models), 'model')})",
            green_bold,
            use_color,
        ),
        "",
    ]
    visible_models: tuple[CompiledModel, ...] = graph.project.models[:_HUMAN_MODEL_LIMIT]
    model_name_width: int = _model_name_width(visible_models)
    for model in visible_models:
        model_name: str = _fit(model.name, width=model_name_width)
        lines.append(
            f"  {_style(model_name, blue_bold, use_color)} "
            f"{_style('OK', green, use_color)} "
            f"{_style(f'{_column_count(model)} columns', dim, use_color)}"
        )
    hidden_model_count: int = len(graph.project.models) - len(visible_models)
    if hidden_model_count > 0:
        lines.append("")
        lines.append(
            "  "
            + _style(
                f"Showing {len(visible_models)} of {len(graph.project.models)} models.",
                dim,
                use_color,
            )
        )
        lines.append("  " + _style("Use --json for the full compile report.", dim, use_color))
    lines.append("")
    lines.append(
        f"  {_style('Compiled:', green_bold, use_color)} "
        f"{_count_label(len(graph.project.models), 'model')}, "
        f"{_count_label(len(graph.project.seeds), 'seed')}, "
        f"{_count_label(len(graph.project.functions), 'function')}, "
        "0 errors, 0 warnings"
    )
    lines.append(
        f"  {_style('Wrote:', dim, use_color)} {_relative_target_path(_compiled_sql_dir(written))}/"
    )
    if manifest:
        lines.append(f"  {_style('Wrote:', dim, use_color)} target/manifest.json")
    if lineage is None and graph.project.settings.sqlglot:
        lines.append(f"  {_style('Column lineage:', yellow, use_color)} unavailable")
    return "\n" + "\n".join(lines) + "\n"


def format_compile_json(
    *,
    graph: ProjectGraph,
    written: WrittenTarget,
    manifest: bool,
    timings_ms: dict[str, int],
    lineage: ProjectColumnLineage | None,
) -> str:
    """Serialize the offline compile report as JSON."""

    result: dict[str, object] = {
        "version": _sqlbuild_version(),
        "command": "compile",
        "offline": True,
        "has_errors": False,
        "summary": _summary(graph),
        "diagnostics": [],
        "compile_timings": timings_ms,
        "resources": _resources(graph=graph, lineage=lineage),
        "artifacts": _artifacts(written=written, manifest=manifest),
    }
    return json.dumps(result, indent=2)


def _summary(graph: ProjectGraph) -> dict[str, int]:
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
        "errors": 0,
        "warnings": 0,
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
    if model.target.qualified_name is not None:
        item["qualified_name"] = model.target.qualified_name
    return item


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
    if seed.target.qualified_name is not None:
        item["qualified_name"] = seed.target.qualified_name
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
    if function.target.qualified_name is not None:
        item["qualified_name"] = function.target.qualified_name
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
    return {
        "name": test.name,
        "relative_path": str(test.test_file.relative_path),
        "expected_models": list(test.expected_model_names),
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


def _serialize_key(key: CompiledObjectKey) -> dict[str, str]:
    return {"resource_type": str(key.resource_type), "name": key.name}


def _execution_layer_count(graph: ProjectGraph) -> int:
    model_keys: set[CompiledObjectKey] = {model.key for model in graph.project.models}
    if not model_keys:
        return 0
    cache: dict[CompiledObjectKey, int] = {}

    def layer_for(key: CompiledObjectKey, visiting: frozenset[CompiledObjectKey]) -> int:
        if key in cache:
            return cache[key]
        if key in visiting:
            return 1
        dep_layers: list[int] = []
        for dep in graph.upstream_deps.get(key, ()):
            if dep in model_keys:
                dep_layers.append(layer_for(dep, visiting | {key}))
        layer: int = 1 + max(dep_layers, default=0)
        cache[key] = layer
        return layer

    return max(layer_for(key, frozenset()) for key in model_keys)


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


def _style(text: str, styler: Callable[[str], str], use_color: bool) -> str:
    if not use_color:
        return text
    return styler(text)
