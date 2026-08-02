"""Source read deferral helpers for managed source loaders."""

from __future__ import annotations

import re
from dataclasses import replace

from sqlbuild.compiler.compile.main._project_var_values import render_project_var_text
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSource,
)
from sqlbuild.compiler.planner.constants import SOURCE_DEFERRAL_CONTEXT_FIELDS
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.references.main._quoted_reference_call_pattern import (
    quoted_reference_call_pattern,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, SourceEntry, TargetConfig

_CTX_PATTERN: re.Pattern[str] = re.compile(r"\$\{CTX:([^}]+)\}")
_VAR_PATTERN: re.Pattern[str] = re.compile(r"\$\{([^}:]+)\}")
_SOURCE_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SOURCE)


def build_source_read_map(
    *,
    project: CompiledProject,
    source_map: dict[str, SourceEntry],
    selected_keys: frozenset[CompiledObjectKey],
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
    defer_sources_to: str | None,
) -> dict[str, SourceEntry]:
    """Resolve the source relation map used when selected SQL reads managed sources."""

    managed_source_names: frozenset[str] = frozenset(
        source.source_entry.name
        for source in project.sources
        if source.source_entry.loader is not None
    )
    selected_managed_sources: tuple[str, ...] = _selected_managed_source_refs(
        project=project,
        selected_keys=selected_keys,
        managed_source_names=managed_source_names,
    )
    if not selected_managed_sources:
        return source_map
    source_target_name: str | None = _resolve_source_target_name(
        project=project,
        project_config=project_config,
        local_config=local_config,
        defer_sources_to=defer_sources_to,
    )
    if source_target_name is None:
        return source_map
    if project_config is None or local_config is None:
        return source_map
    if (
        source_target_name not in project_config.targets
        and source_target_name not in local_config.targets
    ):
        raise PlannerInputError(f"Unknown source deferral target '{source_target_name}'")
    source_target: TargetConfig = resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=source_target_name,
    )
    result: dict[str, SourceEntry] = dict(source_map)
    source: CompiledSource
    for source in project.sources:
        if source.source_entry.name not in selected_managed_sources:
            continue
        raw_source_entry: SourceEntry = _raw_source_entry(source)
        result[source.source_entry.name] = _source_entry_for_environment(
            source_entry=raw_source_entry,
            target_config=source_target,
            effective_vars=project.effective_vars,
        )
    return result


def _selected_managed_source_refs(
    *,
    project: CompiledProject,
    selected_keys: frozenset[CompiledObjectKey],
    managed_source_names: frozenset[str],
) -> tuple[str, ...]:
    names: set[str] = set()
    model: CompiledModel
    for model in project.models:
        if model.key not in selected_keys:
            continue
        names.update(
            _direct_managed_source_refs(
                sql=model.query_sql, managed_source_names=managed_source_names
            )
        )
    function: CompiledFunction
    for function in project.functions:
        if function.key not in selected_keys:
            continue
        names.update(
            _direct_managed_source_refs(
                sql=function.body_sql, managed_source_names=managed_source_names
            )
        )
    audit: CompiledAudit
    for audit in project.audits:
        if audit.scope_deps and not any(dep in selected_keys for dep in audit.scope_deps):
            continue
        for ref in audit.references:
            if ref.ref_kind == SqlReferenceKind.SOURCE and ref.ref_name in managed_source_names:
                names.add(ref.ref_name)
        for match in _SOURCE_PATTERN.finditer(audit.sql_body):
            source_name: str = match.group(1)
            if source_name in managed_source_names:
                names.add(source_name)
    return tuple(sorted(names))


def _direct_managed_source_refs(
    *, sql: str, managed_source_names: frozenset[str]
) -> frozenset[str]:
    names: set[str] = set()
    match: re.Match[str]
    for match in _SOURCE_PATTERN.finditer(sql):
        source_name: str = match.group(1)
        if source_name in managed_source_names:
            names.add(source_name)
    return frozenset(names)


def _resolve_source_target_name(
    *,
    project: CompiledProject,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
    defer_sources_to: str | None,
) -> str | None:
    if defer_sources_to is not None:
        return defer_sources_to
    if project.effective_target_name is None or project_config is None or local_config is None:
        return None
    active_target: TargetConfig = resolve_target_config(
        project_config=project_config,
        local_config=local_config,
        target_name=project.effective_target_name,
    )
    return active_target.defer_sources_to or project.effective_target_name


def _raw_source_entry(source: CompiledSource) -> SourceEntry:
    source_entry: SourceEntry
    for source_entry in source.source_file.source_entries:
        if source_entry.name == source.source_entry.name:
            return source_entry
    return source.source_entry


def _source_entry_for_environment(
    *,
    source_entry: SourceEntry,
    target_config: TargetConfig,
    effective_vars: dict[str, object],
) -> SourceEntry:
    if source_entry.expression is not None:
        return source_entry
    database: str | None = source_entry.database
    if database is None:
        database = _resolve_target_field(
            target_value=target_config.database,
            logical_value=source_entry.database,
            effective_vars=effective_vars,
        )
    schema: str | None = source_entry.schema
    if schema is None:
        schema = _resolve_target_field(
            target_value=target_config.loader_schema or target_config.schema,
            logical_value=source_entry.schema,
            effective_vars=effective_vars,
        )
    return replace(
        source_entry,
        database=database,
        schema=schema,
    )


def _resolve_target_field(
    *, target_value: str | None, logical_value: str | None, effective_vars: dict[str, object]
) -> str | None:
    if target_value is None:
        return logical_value

    def _replace_ctx(match: re.Match[str]) -> str:
        ctx_key: str = match.group(1)
        if ctx_key in SOURCE_DEFERRAL_CONTEXT_FIELDS:
            return logical_value if logical_value is not None else ""
        return match.group(0)

    result: str = _CTX_PATTERN.sub(_replace_ctx, target_value)

    def _replace_var(match: re.Match[str]) -> str:
        var_name: str = match.group(1)
        if var_name not in effective_vars:
            return match.group(0)
        return render_project_var_text(
            value=effective_vars[var_name],
            label=f"source deferral variable '${{{var_name}}}'",
        )

    return _VAR_PATTERN.sub(_replace_var, result)
