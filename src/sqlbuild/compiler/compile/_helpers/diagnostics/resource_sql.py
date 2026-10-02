"""Run the model compile-time SQL checks on audits, SQL tests and SQL hooks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.binding_positions import (
    get_authored_binding_location,
)
from sqlbuild.compiler.compile._helpers.assembly.native_declarations import (
    known_declared_types,
    known_function_names,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import binding_relation_names
from sqlbuild.compiler.compile._helpers.diagnostics.resource_sql_help import resource_sql_help
from sqlbuild.compiler.compile._helpers.diagnostics.sql_analysis_opt_outs import (
    unneeded_opt_out_diagnostic,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
)
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledProject,
    CompiledSqlExpansion,
    CompilerDiagnostic,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.constants import SQL_ANALYSIS_CONFIG_KEY
from sqlbuild.compiler.sql_analysis.constants import BINDING_UNKNOWN_TABLE_INTERNAL_CODE
from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql
from sqlbuild.compiler.sql_analysis.main._resolve_binding_column import resolve_binding_column
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.models import (
    SqlBindingDiagnostic,
    SqlBindingResult,
    SqlSchemaValidationRequest,
)
from sqlbuild.spec.contracts.models import SourceLocation

_MODEL_HOOK_KEYS: tuple[str, ...] = ("pre_hooks", "post_hooks")
_QUOTED_NAME_PATTERN: re.Pattern[str] = re.compile(r"'([^']+)'")
_REFERENCE_CALL_PATTERN: re.Pattern[str] = re.compile(
    r"__(?:ref|source|seed)\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_EMPTY_FIXTURE_CTE_PATTERN: re.Pattern[str] = re.compile(
    r"(?P<prefix>\b__(?:ref|source|seed|expected)__(?P<name>\w+)\s+AS\s*\(\s*SELECT\s+\*\s+FROM\s+)"
    r"__empty_fixture\s*\(\s*\)",
    flags=re.IGNORECASE,
)
_EMPTY_FIXTURE_CALL_PATTERN: re.Pattern[str] = re.compile(
    r"\b__empty_fixture\s*\(\s*\)", flags=re.IGNORECASE
)
_OPEN_EMPTY_FIXTURE_RELATION: str = "__sqlbuild_empty_fixture"
_BUILT_IN_AUDIT_ROOT: str = "<built-in>"
_COLUMN_ONLY_BUILT_IN_AUDITS: frozenset[str] = frozenset({"not_null", "unique"})
_UNKNOWN_TABLE_MESSAGE_PREFIX: str = "Unknown table "
_SYNTAX_ERROR_CODE: str = "P001"
_RESOURCE_KIND_LABELS: dict[CompiledResourceType, str] = {
    CompiledResourceType.AUDIT: "audit",
    CompiledResourceType.SQL_TEST: "SQL test",
    CompiledResourceType.MODEL: "model",
}


@dataclass(frozen=True)
class _ResourceSql:
    """One authored SQL body owned by a non-model resource."""

    resource_type: CompiledResourceType
    resource_name: str
    path: Path
    contents: str
    authored_body: str
    sql: str
    relations: frozenset[str]
    label: str | None = None
    audit_definition: str | None = None
    opt_out: SourceLocation | None = None


@dataclass(frozen=True)
class _HelpContext:
    shapes: dict[str, dict[str, str]]
    dialect: str | None


def get_resource_sql_diagnostics(
    *,
    project: CompiledProject,
    shapes: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
) -> tuple[CompilerDiagnostic, ...]:
    """Bind audits, SQL tests and SQL hooks against the same closed shapes as models."""

    resources: tuple[_ResourceSql, ...] = tuple(
        resource
        for resource in dict.fromkeys(
            (
                *_audit_resources(project=project, shapes=shapes, profile=profile),
                *_sql_test_resources(project=project),
                *_hook_resources(project=project),
            )
        )
        if resource.opt_out is None or project.settings.require_sql_analysis
    )
    if not resources:
        return ()
    dialect: str | None = profile.sql_analysis_dialect
    normalized: dict[str, str] = {}
    for resource in resources:
        if resource.sql not in normalized:
            normalized[resource.sql] = normalize_analysis_sql(
                sql=cursor_intrinsics_analysis_sql(sql=resource.sql, cursor_type=None),
                dialect=dialect,
            )
    cleaned: tuple[str, ...] = tuple(normalized[resource.sql] for resource in resources)
    known_functions: tuple[str, ...] = known_function_names(project.functions)
    known_types: tuple[str, ...] = known_declared_types(
        functions=project.functions, column_types=shapes
    )
    requests: dict[tuple[str, frozenset[str]], SqlSchemaValidationRequest] = {}
    for resource, cleaned_sql in zip(resources, cleaned, strict=True):
        _ = requests.setdefault(
            (cleaned_sql, resource.relations),
            SqlSchemaValidationRequest(
                sql=cleaned_sql,
                dialect=dialect,
                schema=_relation_schema(relations=resource.relations, shapes=shapes),
                known_functions=known_functions,
                known_types=known_types,
                quoted_identifiers_ignore_case=profile.quoted_identifiers_ignore_case,
                catalog=project.binding_catalog,
            ),
        )
    unique_results: dict[tuple[str, frozenset[str]], SqlBindingResult] = dict(
        zip(requests, get_schema_validations(requests=tuple(requests.values())), strict=True)
    )
    results: tuple[SqlBindingResult, ...] = tuple(
        unique_results[(cleaned_sql, resource.relations)]
        for resource, cleaned_sql in zip(resources, cleaned, strict=True)
    )
    diagnostics: dict[tuple[object, ...], CompilerDiagnostic] = {}
    for resource, cleaned_sql, result in zip(resources, cleaned, results, strict=True):
        found: dict[tuple[object, ...], CompilerDiagnostic] = _resource_diagnostics(
            resource=resource,
            cleaned_sql=cleaned_sql,
            result=result,
            context=_HelpContext(shapes=shapes, dialect=dialect),
        )
        if resource.opt_out is None:
            for key, diagnostic in found.items():
                diagnostics.setdefault(key, diagnostic)
        elif not any(item.code == _SYNTAX_ERROR_CODE for item in found.values()):
            diagnostics.setdefault(
                (resource.opt_out.path, resource.opt_out.line, resource.opt_out.column),
                unneeded_opt_out_diagnostic(
                    resource_type=resource.resource_type,
                    kind=_RESOURCE_KIND_LABELS[resource.resource_type],
                    name=resource.resource_name,
                    location=resource.opt_out,
                    hidden=tuple(found.values()),
                ),
            )
    return tuple(diagnostics.values())


def _resource_diagnostics(
    *,
    resource: _ResourceSql,
    cleaned_sql: str,
    result: SqlBindingResult,
    context: _HelpContext,
) -> dict[tuple[object, ...], CompilerDiagnostic]:
    found: dict[tuple[object, ...], CompilerDiagnostic] = {}
    for index, native in enumerate(result.diagnostics):
        diagnostic: SqlBindingDiagnostic | None = _reported_diagnostic(
            resource=resource, diagnostic=native
        )
        if diagnostic is None:
            continue
        location: SourceLocation = _location(
            resource=resource, cleaned_sql=cleaned_sql, diagnostic=diagnostic
        )
        key: tuple[object, ...] = (
            resource.path,
            diagnostic.code,
            diagnostic.message,
            location.line,
            location.column,
            index if diagnostic.start is None else -1,
        )
        found.setdefault(
            key,
            CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity(diagnostic.severity),
                code=diagnostic.code,
                message=diagnostic.message
                if resource.label is None or diagnostic.code == _SYNTAX_ERROR_CODE
                else f"{resource.label}: {diagnostic.message}",
                resource_type=resource.resource_type,
                resource_name=resource.resource_name,
                location=location,
                help=resource_sql_help(
                    resource_type=resource.resource_type,
                    diagnostic=diagnostic,
                    authored_text=_text_from(resource=resource, location=location),
                    authored_line=_line_at(resource=resource, location=location),
                    column=location.column,
                    authored_body=resource.authored_body,
                    audit_definition=resource.audit_definition,
                    shapes=context.shapes,
                    relations=resource.relations,
                    dialect=context.dialect,
                ),
            ),
        )
    return found


def _relation_schema(
    *, relations: frozenset[str], shapes: dict[str, dict[str, str]]
) -> dict[str, dict[str, str]]:
    """Return closed shapes for referenced relations; an empty shape stays open."""

    return {name: shapes.get(name) or {} for name in relations}


def _reported_diagnostic(
    *, resource: _ResourceSql, diagnostic: SqlBindingDiagnostic
) -> SqlBindingDiagnostic | None:
    """Drop open-relation lookups and turn parser rejections into syntax errors."""

    if diagnostic.code != BINDING_UNKNOWN_TABLE_INTERNAL_CODE:
        return diagnostic
    if diagnostic.message.startswith(_UNKNOWN_TABLE_MESSAGE_PREFIX):
        return None
    return SqlBindingDiagnostic(
        code=_SYNTAX_ERROR_CODE,
        message=(
            f"SQL syntax error in {_RESOURCE_KIND_LABELS[resource.resource_type]} "
            f"'{resource.resource_name}': {diagnostic.message}"
        ),
        line=diagnostic.line,
        column=diagnostic.column,
        start=diagnostic.start,
        end=diagnostic.end,
    )


def _audit_resources(
    *,
    project: CompiledProject,
    shapes: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
) -> tuple[_ResourceSql, ...]:
    analysis_disabled: frozenset[str] = _analysis_disabled_models(project)
    resources: list[_ResourceSql] = []
    for audit in project.audits:
        if audit.attached_target_name in analysis_disabled or _binds_cleanly(
            audit=audit, shapes=shapes, profile=profile
        ):
            continue
        relations: frozenset[str] = _relations(audit.references)
        authored_bodies: tuple[str | None, ...] = (
            audit.audit_block.sql_body,
            audit.audit_block.measure_sql,
            audit.audit_block.evidence_sql,
        )
        for sql, authored in zip(
            (audit.sql_body, audit.measure_sql, audit.evidence_sql), authored_bodies, strict=True
        ):
            if not sql or not sql.strip():
                continue
            body: str = authored or sql
            resources.append(
                _ResourceSql(
                    resource_type=CompiledResourceType.AUDIT,
                    resource_name=audit.name,
                    path=audit.audit_file.relative_path,
                    contents=audit.audit_file.contents,
                    authored_body=body,
                    sql=sql,
                    relations=relations,
                    label=_audit_label(audit),
                    audit_definition=audit.definition_name,
                    opt_out=_header_opt_out(
                        header_values=audit.audit_block.header_values,
                        path=audit.audit_file.relative_path,
                        contents=audit.audit_file.contents,
                        body=body,
                    ),
                )
            )
    return tuple(resources)


def _binds_cleanly(
    *, audit: CompiledAudit, shapes: dict[str, dict[str, str]], profile: ExpressionInferenceProfile
) -> bool:
    """A built-in single-column audit on a column its closed target shape contains."""

    if (
        audit.definition_name not in _COLUMN_ONLY_BUILT_IN_AUDITS
        or audit.audit_file.file_path.parts[:1] != (_BUILT_IN_AUDIT_ROOT,)
        or audit.attached_target_name is None
        or audit.attached_column_name is None
    ):
        return False
    shape: dict[str, str] = shapes.get(audit.attached_target_name) or {}
    return bool(shape) and (
        resolve_binding_column(
            name=audit.attached_column_name,
            columns=shape,
            dialect=profile.sql_analysis_dialect,
            ignore_quoted_case=profile.quoted_identifiers_ignore_case,
        )
        is not None
    )


def _audit_label(audit: CompiledAudit) -> str:
    label: str = f"audit '{audit.definition_name}'"
    if audit.attached_target_name is not None:
        label += f" on {audit.attached_target_kind} '{audit.attached_target_name}'"
    if audit.attached_column_name is not None:
        label += f" column '{audit.attached_column_name}'"
    return label


def _sql_test_resources(*, project: CompiledProject) -> tuple[_ResourceSql, ...]:
    analysis_disabled: frozenset[str] = _analysis_disabled_models(project)
    resources: list[_ResourceSql] = []
    prepared: dict[str, tuple[str, frozenset[str]]] = {}
    for test in project.sql_tests:
        if not test.sql_body.strip() or analysis_disabled.intersection(test.expected_model_names):
            continue
        if test.sql_body not in prepared:
            prepared[test.sql_body] = _prepared_test_sql(test.sql_body)
        sql, relations = prepared[test.sql_body]
        resources.append(
            _ResourceSql(
                resource_type=CompiledResourceType.SQL_TEST,
                resource_name=test.name,
                path=test.test_file.relative_path,
                contents=test.test_file.contents,
                authored_body=test.test_block.sql_body,
                sql=sql,
                label=f"SQL test '{test.name}'",
                opt_out=_header_opt_out(
                    header_values=test.test_block.header_values,
                    path=test.test_file.relative_path,
                    contents=test.test_file.contents,
                    body=test.test_block.sql_body,
                ),
                relations=relations,
            )
        )
    return tuple(resources)


def _prepared_test_sql(sql_body: str) -> tuple[str, frozenset[str]]:
    """Test SQL with empty fixtures opened, and the relations it reads."""

    sql: str = _EMPTY_FIXTURE_CTE_PATTERN.sub(
        lambda match: match.group("prefix") + match.group("name"), sql_body
    )
    return _EMPTY_FIXTURE_CALL_PATTERN.sub(_OPEN_EMPTY_FIXTURE_RELATION, sql), frozenset(
        (
            *_REFERENCE_CALL_PATTERN.findall(sql_body),
            *(match.group("name") for match in _EMPTY_FIXTURE_CTE_PATTERN.finditer(sql_body)),
        )
    )


def _hook_resources(*, project: CompiledProject) -> tuple[_ResourceSql, ...]:
    hook_files: dict[Path, str] = {
        hook_file.relative_path: hook_file.contents for hook_file in project.sql_hook_files
    }
    resources: list[_ResourceSql] = []
    for model in project.models:
        if model.config.values.get(SQL_ANALYSIS_CONFIG_KEY) is False:
            continue
        for hook_key in _MODEL_HOOK_KEYS:
            entries: object = model.config.values.get(hook_key)
            if not isinstance(entries, list | tuple):
                continue
            for hook_index, entry in enumerate(entries):
                statement: object = getattr(entry, "statement", None)
                if not isinstance(statement, str) or not statement.strip():
                    continue
                hook_path: Path | None = getattr(entry, "relative_path", None)
                definition: object = getattr(entry, "definition_sql", None)
                named: bool = hook_path is not None and hook_path in hook_files
                resources.append(
                    _ResourceSql(
                        resource_type=CompiledResourceType.MODEL,
                        resource_name=model.name,
                        path=hook_path if named and hook_path is not None else model.relative_path,
                        contents=hook_files[hook_path]
                        if named and hook_path is not None
                        else model.authored_sql,
                        authored_body=definition
                        if named and isinstance(definition, str)
                        else statement,
                        sql=statement,
                        relations=_relations(tuple(getattr(entry, "reads", ()) or ()))
                        | frozenset(_REFERENCE_CALL_PATTERN.findall(statement)),
                        label=f"{hook_key}[{hook_index}] SQL hook",
                    )
                )
    return tuple(resources)


def _analysis_disabled_models(project: CompiledProject) -> frozenset[str]:
    return frozenset(
        model.name
        for model in project.models
        if model.config.values.get(SQL_ANALYSIS_CONFIG_KEY) is False
    )


def _header_opt_out(
    *, header_values: dict[str, object], path: Path, contents: str, body: str
) -> SourceLocation | None:
    """Where a TEST or AUDIT header turns SQL analysis off, if it does."""

    if header_values.get(SQL_ANALYSIS_CONFIG_KEY) is not False:
        return None
    body_offset: int = contents.find(body)
    key_offset: int = contents.rfind(
        SQL_ANALYSIS_CONFIG_KEY, 0, body_offset if body_offset >= 0 else len(contents)
    )
    return _offset_location(path=path, text=contents, offset=max(key_offset, 0))


def _relations(references: tuple[CompileSqlReference, ...]) -> frozenset[str]:
    return binding_relation_names(
        tuple(reference for reference in references if isinstance(reference, CompileSqlReference))
    )


def _location(
    *, resource: _ResourceSql, cleaned_sql: str, diagnostic: SqlBindingDiagnostic
) -> SourceLocation:
    """Point at the offending authored text, falling back to the body start."""

    body_offset: int = max(resource.contents.find(resource.authored_body), 0)
    if diagnostic.start is None:
        name_offset: int | None = _quoted_name_offset(
            text=resource.contents, start=body_offset, message=diagnostic.message
        )
        if name_offset is not None:
            return _offset_location(path=resource.path, text=resource.contents, offset=name_offset)
    location: SourceLocation | None = get_authored_binding_location(
        path=resource.path,
        authored_sql=resource.contents,
        authored_query_sql=resource.authored_body,
        cleaned_sql=cleaned_sql,
        diagnostic=diagnostic,
        expansion=CompiledSqlExpansion(
            authored_sql=resource.authored_body, expanded_sql=resource.sql, passes=()
        ),
    )
    if location is not None:
        return location
    return _offset_location(path=resource.path, text=resource.contents, offset=body_offset)


def _quoted_name_offset(*, text: str, start: int, message: str) -> int | None:
    for name in _QUOTED_NAME_PATTERN.findall(message):
        identifier: str = name.rsplit(".", 1)[-1]
        match: re.Match[str] | None = re.search(
            rf"(?<!\w){re.escape(identifier)}(?!\w)", text[start:], flags=re.IGNORECASE
        )
        if match is not None:
            return start + match.start()
    return None


def _text_from(*, resource: _ResourceSql, location: SourceLocation) -> str:
    """Authored text of a diagnostic span (or from its start), for help that quotes the source."""

    if location.path != resource.path:
        return ""
    start: int | None = _offset(text=resource.contents, line=location.line, column=location.column)
    if start is None:
        return ""
    end: int | None = (
        _offset(text=resource.contents, line=location.end_line, column=location.end_column)
        if location.end_line is not None and location.end_column is not None
        else None
    )
    return resource.contents[start : end if end is not None and end > start else None]


def _line_at(*, resource: _ResourceSql, location: SourceLocation) -> str:
    lines: list[str] = resource.contents.splitlines()
    if location.path != resource.path or not 1 <= location.line <= len(lines):
        return ""
    return lines[location.line - 1]


def _offset(*, text: str, line: int, column: int) -> int | None:
    lines: list[str] = text.splitlines(keepends=True)
    if not 1 <= line <= len(lines):
        return None
    return sum(len(value) for value in lines[: line - 1]) + max(column - 1, 0)


def _offset_location(*, path: Path, text: str, offset: int) -> SourceLocation:
    line: int = text.count("\n", 0, offset) + 1
    column: int = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return SourceLocation(path=path, line=line, column=column)
