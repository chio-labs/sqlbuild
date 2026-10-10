"""Hand the native rules request builder rows read from the Python compiled project."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import cast

import orjson

import sqlbuild._native as _native
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSqlScenario,
    CompiledSqlTest,
    CompileSqlTestCte,
    DynamicColumnContractProof,
)
from sqlbuild.compiler.discovery.models import ConstantDeclaration, EnumDeclaration
from sqlbuild.compiler.frontier.main.compiled_code_identity import compiled_code_identity
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.scopes.main.scope_metadata import scope_metadata_projection
from sqlbuild.rule_engine._helpers.run.cache_paths import rules_bulk_cache_path
from sqlbuild.rule_engine.constants import (
    NATIVE_RULES_CACHE_FILE,
    NATIVE_RULES_MEMO_FILE,
    RULES_NATIVE_API_VERSION,
)
from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import Finding, NativeRulesEvaluation, RulesConfig
from sqlbuild.rule_engine.types import FindingRow
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind


def build_rules_request(
    *,
    project: CompiledProject,
    config: RulesConfig,
    project_dir: Path,
    dialect: str,
    initial_findings: tuple[Finding, ...],
    custom_payloads: list[dict[str, object]],
    include_type_proof: bool,
) -> _native.NativeRulesRequest:
    """Build the built-in rules request natively from the compiled project's rows."""

    resolved: Path = project_dir.resolve()
    header: dict[str, object] = {
        "version": RULES_NATIVE_API_VERSION,
        "project_dir": str(resolved),
        "dialect": dialect,
        "config": asdict(config),
        "scope_index": scope_metadata_projection(index=project.scope_index),
        "defer_suppressions": True,
        "custom_rules": custom_payloads,
        "rules_cache_path": str(
            rules_bulk_cache_path(project_dir=resolved, file_name=NATIVE_RULES_CACHE_FILE)
        ),
    }
    project_rows: dict[str, object] = {
        "header_json": _encoded(header),
        "memo": (
            (
                compiled_code_identity(),
                str(
                    rules_bulk_cache_path(project_dir=project_dir, file_name=NATIVE_RULES_MEMO_FILE)
                ),
            )
            if config.cache.enabled
            else None
        ),
        "sql_analysis_enabled": project.settings.sql_analysis,
        "include_type_proof": include_type_proof,
        "attached_audit_targets": [
            audit.attached_target_name
            for audit in project.audits
            if audit.attached_target_name is not None
        ],
        "public_enums": [_enum_row(declaration) for declaration in project.public_enums.values()],
        "public_constants": [
            _constant_row(declaration) for declaration in project.public_constants.values()
        ],
        "initial_findings": [finding_row(finding) for finding in initial_findings],
        "types_equal": partial(types_equal, dialect=dialect),
    }
    try:
        request: _native.NativeRulesRequest
        counts: tuple[int, int, int]
        request, counts = _native.build_rules_request(
            project_rows,
            [_model_row(model) for model in project.models],
            [_sql_test_row(test) for test in project.sql_tests],
            [_scenario_row(scenario) for scenario in project.sql_scenarios],
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    for kind, units in zip(("models", "sql_tests", "sql_scenarios"), counts, strict=True):
        report_native_answer(stage=NativeStage.RULES_REQUEST, kind=kind, units=units)
    return request


def evaluate_rules_request(request: _native.NativeRulesRequest) -> NativeRulesEvaluation:
    """Answer the request from the response memo or evaluate it, decoding findings natively."""

    try:
        faults, selected_codes, evaluated, hits, misses, built_in_ms, reused = (
            _native.evaluate_rules_request(request)
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    return NativeRulesEvaluation(
        findings=tuple(finding_from_row(row) for row in faults),
        selected_codes=tuple(selected_codes),
        evaluated_models=evaluated,
        cache_hits=hits,
        cache_misses=misses,
        built_in_ms=built_in_ms,
        reused=reused,
    )


def finalize_rules_rows(
    *,
    config: RulesConfig,
    project_dir: Path,
    evaluated_codes: tuple[str, ...],
    findings: tuple[Finding, ...],
) -> tuple[Finding, ...]:
    """Apply the exception policy natively to finding rows."""

    try:
        rows: list[FindingRow] = _native.finalize_rule_findings_rows(
            {
                "project_dir": str(project_dir.resolve()),
                "config_json": _encoded(asdict(config)),
                "evaluated_codes": list(evaluated_codes),
                "findings": [finding_row(finding) for finding in findings],
            }
        )
    except (ValueError, TypeError) as error:
        raise RulesError(str(error)) from error
    return tuple(finding_from_row(row) for row in rows)


def finding_row(finding: Finding) -> FindingRow:
    """One finding as the native boundary's row."""

    return (
        finding.unevaluated,
        finding.code,
        finding.path.as_posix(),
        finding.line,
        finding.column,
        finding.message,
        finding.remediation,
    )


def finding_from_row(row: FindingRow) -> Finding:
    """One native finding row as a finding."""

    unevaluated, code, path, line, column, message, remediation = row
    return Finding(
        code=code,
        path=Path(path),
        line=line,
        column=column,
        message=message,
        remediation=remediation,
        unevaluated=unevaluated,
    )


def typed_value_payload(value: SqlValue) -> object:
    """A typed SQL value as the plain value the rules request carries."""

    if value.kind == SqlValueKind.DECIMAL:
        return str(cast(Decimal, value.value))
    if value.kind in {
        SqlValueKind.STRING,
        SqlValueKind.INTEGER,
        SqlValueKind.BOOLEAN,
        SqlValueKind.FLOAT,
        SqlValueKind.NULL,
    }:
        return value.value
    if value.kind in {SqlValueKind.LIST, SqlValueKind.SET}:
        return [typed_value_payload(item) for item in cast(tuple[SqlValue, ...], value.value)]
    return {
        key: typed_value_payload(item)
        for key, item in cast(tuple[tuple[str, SqlValue], ...], value.value)
    }


def _encoded(value: object) -> bytes:
    try:
        return orjson.dumps(value, option=orjson.OPT_SORT_KEYS, default=str)
    except orjson.JSONEncodeError as error:
        raise RulesError(str(error)) from error


def _model_row(model: CompiledModel) -> tuple[object, ...]:
    schema: object = None
    if model.schema_entry is not None:
        schema = (
            len(model.schema_entry.audits),
            [
                (column.name, column.type, column.nullable, len(column.audits))
                for column in model.schema_entry.columns
            ],
            [
                (
                    family.name.casefold(),
                    family.name,
                    family.pivot_column,
                    family.value_column,
                    family.aggregate,
                    family.type,
                    family.name_pattern,
                )
                for family in model.schema_entry.dynamic_columns
            ],
        )
    proof: DynamicColumnContractProof | None = model.dynamic_column_contract
    return (
        (
            model.name,
            model.relative_path.as_posix(),
            model.query_sql,
            model.authored_query_sql or model.authored_sql,
        ),
        _encoded(model.config.values),
        list(model.config.model_header_keys),
        model.config.layer_schema,
        [
            (str(reference.ref_kind), reference.ref_name, reference.ref_package)
            for reference in model.references
        ],
        schema,
        [(column.name, column.type) for column in (model.inferred_columns or ())],
        None
        if proof is None
        else (
            proof.output_proven,
            proof.bare_dynamic_pivot,
            [(family.name.casefold(), family.inferred_type) for family in proof.families],
        ),
        list(model.enum_columns),
        (
            [_enum_row(declaration) for declaration in model.enum_declarations],
            [_constant_row(declaration) for declaration in model.constant_declarations],
        ),
    )


def _enum_row(declaration: EnumDeclaration) -> tuple[object, ...]:
    return (
        declaration.name,
        declaration.relative_path.as_posix(),
        [(member.name, member.value) for member in declaration.members],
        None,
        None,
        None,
    )


def _constant_row(declaration: ConstantDeclaration) -> tuple[object, ...]:
    return (
        declaration.name,
        declaration.relative_path.as_posix(),
        [],
        typed_value_payload(declaration.value),
        declaration.logical_type.display_name,
        declaration.render_as.value if declaration.render_as is not None else None,
    )


def _sql_test_row(test: CompiledSqlTest) -> tuple[object, ...]:
    payload: object = (
        (
            _cte_rows(test.payload.authored_ctes),
            _cte_rows(test.payload.expected_ctes),
            _cte_rows(test.payload.assertion_ctes),
            bool(test.payload.macro_mocks),
            bool(test.payload.model_query_overrides),
        )
        if isinstance(test.payload, CompiledModelSqlTestPayload)
        else None
    )
    case: object = (
        None
        if test.case_name is None
        else (
            test.parent_name,
            test.case_name,
            test.case_index,
            test.case_fingerprint,
            [
                (parameter.name, parameter.value_type.value, parameter.nullable)
                for parameter in test.parameter_schema
            ],
            [(name, typed_value_payload(value)) for name, value in test.parameter_values],
        )
    )
    return (
        (test.source_path or test.test_file.relative_path).as_posix(),
        (test.ownership_root or test.test_file.ownership_root).as_posix(),
        test.block_index or test.test_block.test_index,
        test.name,
        test.explicit_name,
        test.mode.value,
        (
            list(test.expected_model_names),
            list(test.assertion_names),
            list(test.assertion_target_model_names),
            list(test.target_model_names),
        ),
        [(resource.kind.value, resource.name) for resource in test.tested_resources],
        payload,
        case,
    )


def _cte_rows(ctes: tuple[CompileSqlTestCte, ...]) -> list[tuple[str, str]]:
    return [(cte.name, cte.sql_body) for cte in ctes]


def _scenario_row(scenario: CompiledSqlScenario) -> tuple[object, ...]:
    description: object | None = scenario.scenario_file.header_values.get("description")
    return (
        (scenario.source_path or scenario.scenario_file.relative_path).as_posix(),
        (scenario.ownership_root or scenario.scenario_file.ownership_root).as_posix(),
        scenario.name,
        description if isinstance(description, str) else None,
        list(scenario.expected_model_names),
        list(scenario.assertion_names),
        list(scenario.assertion_target_model_names),
        list(scenario.target_model_names),
    )
