"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile._helpers.analysis.validation import (
    validate_source_expression_syntax,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import reject_cursor_intrinsics
from sqlbuild.compiler.compile._helpers.render.sql_vars import (
    expand_authored_sql,
)
from sqlbuild.compiler.compile._helpers.render.templating import (
    expand_template_data,
)
from sqlbuild.compiler.compile.models import (
    CompileSourceInput,
    DeclarationExpansionContext,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSourceFile,
)
from sqlbuild.spec.contracts.models import (
    SchemaAuditInstance,
    SettingsConfig,
    SourceColumnEntry,
    SourceEntry,
)

_HOOK_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{[^}]+\}")
_LEGACY_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hook", "post_hook"})
_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_HOOK_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset(
    {"ctx", "context", "_ctx", "hook_context"}
)


def build_source_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_vars: dict[str, object],
    effective_settings: SettingsConfig,
    macro_context: MacroContext,
    loaded_macros: dict[str, LoadedMacro],
    declaration_expansion: DeclarationExpansionContext,
    no_sql_validation: bool = False,
) -> tuple[CompileSourceInput, ...]:
    """Normalize discovered source declarations into one collection."""

    source_inputs: list[CompileSourceInput] = []
    sql_validation_enabled: bool = (
        effective_settings.sql_analysis
        and effective_settings.sql_validation
        and not no_sql_validation
    )
    source_file: DiscoveredSourceFile
    for source_file in discovered_inputs.source_files:
        source_entry: SourceEntry
        for raw_source_entry in source_file.source_entries:
            source_entry = expand_source_entry_templates(
                source_entry=raw_source_entry,
                file_path=source_file.file_path,
                effective_vars=effective_vars,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
                declaration_expansion=declaration_expansion,
            )
            source_expression: str | None = source_entry.expression
            if source_expression is not None:
                reject_cursor_intrinsics(
                    sql=source_expression,
                    context=f"Source expression '{source_entry.name}'",
                )
            should_validate_expression: bool = (
                source_expression is not None and sql_validation_enabled
            )
            if should_validate_expression and source_expression is not None:
                validate_source_expression_syntax(
                    expression=source_expression,
                    source_name=source_entry.name,
                    file_path=source_file.file_path,
                )
            source_inputs.append(
                CompileSourceInput(
                    source_entry=source_entry,
                    source_file=source_file,
                )
            )
    return tuple(source_inputs)


def expand_source_entry_templates(
    *,
    source_entry: SourceEntry,
    file_path: Path,
    effective_vars: dict[str, object],
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
    declaration_expansion: DeclarationExpansionContext,
) -> SourceEntry:
    """Apply config templating and SQL interpolation to source metadata."""

    expression: str | None = None
    if source_entry.expression is not None:
        expression = expand_authored_sql(
            sql=source_entry.expression,
            file_path=file_path,
            effective_vars=effective_vars,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
            enums=declaration_expansion.declarations.enums,
            constants=declaration_expansion.declarations.constants,
            value_renderer=declaration_expansion.value_renderer,
            collection_rendering=declaration_expansion.collection_rendering,
        )
    return replace(
        source_entry,
        database=_expand_source_template_value(
            raw_value=source_entry.database,
            effective_vars=effective_vars,
            context_label=f"source {source_entry.name} database",
        ),
        schema=_expand_source_template_value(
            raw_value=source_entry.schema,
            effective_vars=effective_vars,
            context_label=f"source {source_entry.name} schema",
        ),
        table=_expand_source_template_value(
            raw_value=source_entry.table,
            effective_vars=effective_vars,
            context_label=f"source {source_entry.name} table",
        ),
        expression=expression,
        description=_expand_source_template_value(
            raw_value=source_entry.description,
            effective_vars=effective_vars,
            context_label=f"source {source_entry.name} description",
        ),
        meta=cast(
            dict[str, object],
            _expand_source_template_object(
                value=source_entry.meta,
                effective_vars=effective_vars,
                context_label=f"source {source_entry.name} meta",
            ),
        ),
        columns=tuple(
            expand_source_column_templates(
                source_name=source_entry.name,
                column=column,
                effective_vars=effective_vars,
            )
            for column in source_entry.columns
        ),
        audits=tuple(
            expand_schema_audit_instance_templates(
                audit_instance=audit_instance,
                effective_vars=effective_vars,
                context_label=f"source {source_entry.name} audit {audit_instance.definition_name}",
            )
            for audit_instance in source_entry.audits
        ),
    )


def expand_source_column_templates(
    *, source_name: str, column: SourceColumnEntry, effective_vars: dict[str, object]
) -> SourceColumnEntry:
    return replace(
        column,
        type=_expand_source_template_value(
            raw_value=column.type,
            effective_vars=effective_vars,
            context_label=f"source {source_name} column {column.name} type",
        ),
        description=_expand_source_template_value(
            raw_value=column.description,
            effective_vars=effective_vars,
            context_label=f"source {source_name} column {column.name} description",
        ),
        meta=cast(
            dict[str, object],
            _expand_source_template_object(
                value=column.meta,
                effective_vars=effective_vars,
                context_label=f"source {source_name} column {column.name} meta",
            ),
        ),
        audits=tuple(
            expand_schema_audit_instance_templates(
                audit_instance=audit_instance,
                effective_vars=effective_vars,
                context_label=(
                    f"source {source_name} column {column.name} audit "
                    f"{audit_instance.definition_name}"
                ),
            )
            for audit_instance in column.audits
        ),
    )


def expand_schema_audit_instance_templates(
    *,
    audit_instance: SchemaAuditInstance,
    effective_vars: dict[str, object],
    context_label: str,
) -> SchemaAuditInstance:
    return replace(
        audit_instance,
        arguments=cast(
            dict[str, object],
            _expand_source_template_object(
                value=audit_instance.arguments,
                effective_vars=effective_vars,
                context_label=f"{context_label} arguments",
            ),
        ),
        description=_expand_source_template_value(
            raw_value=audit_instance.description,
            effective_vars=effective_vars,
            context_label=f"{context_label} description",
        ),
    )


def _expand_source_template_value(
    *, raw_value: str | None, effective_vars: dict[str, object], context_label: str
) -> str | None:
    if raw_value is None:
        return None
    return str(
        _expand_source_template_object(
            value=raw_value,
            effective_vars=effective_vars,
            context_label=context_label,
        )
    )


def _expand_source_template_object(
    *, value: object, effective_vars: dict[str, object], context_label: str
) -> object:
    return expand_template_data(
        value=value,
        variables=effective_vars,
        context_values={},
        context_label=context_label,
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
    )
