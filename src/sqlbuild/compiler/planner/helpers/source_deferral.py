"""Source read deferral helpers for managed source loaders."""

from __future__ import annotations

import re
from dataclasses import replace

from sqlbuild.compiler.compile.models.core import (
    CompiledAudit,
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSource,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.helpers.project_var_values import render_project_var_text
from sqlbuild.shared.helpers.sql_reference_patterns import quoted_reference_call_pattern
from sqlbuild.shared.types import SqlReferenceKind
from sqlbuild.spec.models.project import (
    ClonePolicy,
    EnvironmentConfig,
    LocalConfig,
    LocalEnvironmentConfig,
    ProjectConfig,
)
from sqlbuild.spec.models.source import SourceEntry

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
    source_environment_name: str | None = _resolve_source_environment_name(
        project=project,
        project_config=project_config,
        local_config=local_config,
        defer_sources_to=defer_sources_to,
    )
    if source_environment_name is None and project.effective_environment_name is None:
        return source_map
    if source_environment_name is None:
        raise PlannerInputError(
            _missing_source_deferral_message(project.effective_environment_name)
        )
    if project_config is None or local_config is None:
        raise PlannerInputError(
            _missing_source_deferral_message(project.effective_environment_name)
        )
    if (
        source_environment_name not in project_config.environments
        and source_environment_name not in local_config.environments
    ):
        raise PlannerInputError(f"Unknown source deferral environment '{source_environment_name}'")
    source_environment: EnvironmentConfig = _resolve_environment_config(
        project_config=project_config,
        local_config=local_config,
        environment_name=source_environment_name,
    )
    result: dict[str, SourceEntry] = dict(source_map)
    source: CompiledSource
    for source in project.sources:
        if source.source_entry.name not in selected_managed_sources:
            continue
        raw_source_entry: SourceEntry = _raw_source_entry(source)
        result[source.source_entry.name] = _source_entry_for_environment(
            source_entry=raw_source_entry,
            environment_config=source_environment,
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
        for ref in model.references:
            if ref.ref_kind == SqlReferenceKind.SOURCE and ref.ref_name in managed_source_names:
                names.add(ref.ref_name)
    function: CompiledFunction
    for function in project.functions:
        if function.key not in selected_keys:
            continue
        for ref in function.references:
            if ref.ref_kind == SqlReferenceKind.SOURCE and ref.ref_name in managed_source_names:
                names.add(ref.ref_name)
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


def _resolve_source_environment_name(
    *,
    project: CompiledProject,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
    defer_sources_to: str | None,
) -> str | None:
    if defer_sources_to is not None:
        return defer_sources_to
    if project.effective_environment_name is None or project_config is None or local_config is None:
        return None
    active_environment: EnvironmentConfig = _resolve_environment_config(
        project_config=project_config,
        local_config=local_config,
        environment_name=project.effective_environment_name,
    )
    return active_environment.defer_sources_to


def _resolve_environment_config(
    *, project_config: ProjectConfig, local_config: LocalConfig, environment_name: str
) -> EnvironmentConfig:
    project_environment: EnvironmentConfig = project_config.environments.get(
        environment_name, EnvironmentConfig()
    )
    local_environment: LocalEnvironmentConfig | None = local_config.environments.get(
        environment_name
    )
    if local_environment is None:
        return project_environment
    return EnvironmentConfig(
        connection={**project_environment.connection, **local_environment.connection},
        vars={**project_environment.vars, **local_environment.vars},
        database=(
            local_environment.database
            if local_environment.database is not None
            else project_environment.database
        ),
        schema=(
            local_environment.schema
            if local_environment.schema is not None
            else project_environment.schema
        ),
        defer_sources_to=(
            local_environment.defer_sources_to
            if local_environment.defer_sources_to is not None
            else project_environment.defer_sources_to
        ),
        clone=ClonePolicy(
            allow_as_source=(
                local_environment.clone.allow_as_source
                if local_environment.clone.allow_as_source is not None
                else project_environment.clone.allow_as_source
            ),
            allow_as_target=(
                local_environment.clone.allow_as_target
                if local_environment.clone.allow_as_target is not None
                else project_environment.clone.allow_as_target
            ),
        ),
    )


def _raw_source_entry(source: CompiledSource) -> SourceEntry:
    source_entry: SourceEntry
    for source_entry in source.source_file.source_entries:
        if source_entry.name == source.source_entry.name:
            return source_entry
    return source.source_entry


def _source_entry_for_environment(
    *,
    source_entry: SourceEntry,
    environment_config: EnvironmentConfig,
    effective_vars: dict[str, object],
) -> SourceEntry:
    if source_entry.expression is not None:
        return source_entry
    database: str | None = source_entry.database
    if database is None:
        database = _resolve_env_field(
            env_value=environment_config.database,
            logical_value=source_entry.database,
            effective_vars=effective_vars,
        )
    schema: str | None = source_entry.schema
    if schema is None:
        schema = _resolve_env_field(
            env_value=environment_config.schema,
            logical_value=source_entry.schema,
            effective_vars=effective_vars,
        )
    return replace(
        source_entry,
        database=database,
        schema=schema,
    )


def _resolve_env_field(
    *, env_value: str | None, logical_value: str | None, effective_vars: dict[str, object]
) -> str | None:
    if env_value is None:
        return logical_value

    def _replace_ctx(match: re.Match[str]) -> str:
        ctx_key: str = match.group(1)
        if ctx_key in ("schema", "database"):
            return logical_value if logical_value is not None else ""
        return match.group(0)

    result: str = _CTX_PATTERN.sub(_replace_ctx, env_value)

    def _replace_var(match: re.Match[str]) -> str:
        var_name: str = match.group(1)
        if var_name not in effective_vars:
            return match.group(0)
        return render_project_var_text(
            value=effective_vars[var_name],
            label=f"source deferral variable '${{{var_name}}}'",
        )

    return _VAR_PATTERN.sub(_replace_var, result)


def _missing_source_deferral_message(environment_name: str | None) -> str:
    active_environment: str = environment_name if environment_name is not None else "<none>"
    example_environment: str = environment_name if environment_name is not None else "dev"
    return (
        f"Missing source deferral config for environment '{active_environment}'.\n\n"
        "This project has sources with loaders. A loader writes data to the active "
        "environment, but models may need to read source data from another environment. "
        "SQLBuild will not guess.\n\n"
        "Add one of these:\n\n"
        f"    [environments.{example_environment}]\n"
        '    defer_sources_to = "prod"  # example: read production source data in dev\n\n'
        "or:\n\n"
        f"    [environments.{example_environment}]\n"
        f'    defer_sources_to = "{example_environment}"   '
        f"# read source data loaded into {example_environment}"
    )
