"""SQL tests, scenarios and audits attached natively by the compile's model loop."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.auditing.main._builtins import builtin_audit_definitions
from sqlbuild.compiler.auditing.types import AuditEvaluationMode
from sqlbuild.compiler.compile.classes.sql_test_cte_locator import SqlTestCteLocator
from sqlbuild.compiler.compile.classes.sql_test_scan_cache import SqlTestScanCache
from sqlbuild.compiler.compile.constants import SQL_TEST_CTE_SCAN_ALGORITHM
from sqlbuild.compiler.compile.models import (
    CompileDirectLogicSqlTestInputPayload,
    CompileModelSqlTestInputPayload,
    CompilerDiagnostic,
    CompileSqlScenarioCte,
    CompileSqlScenarioInput,
    CompileSqlTestCte,
    CompileSqlTestInput,
)
from sqlbuild.compiler.compile.types import AuditInput, SqlTestMode, TypedSqlValueRenderer
from sqlbuild.compiler.compiled_project._helpers import sql_test_text
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.compiler.scopes.models import DeclarationIdentity
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind, UsageKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import SettingsConfig
from sqlbuild.sql_values.exceptions import SqlValueRenderingError, SqlValueValidationError
from sqlbuild.sql_values.models import SqlValue


def attach_sql_tests_impl(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
    value_renderer: TypedSqlValueRenderer,
    syntax: SqlLexicalSyntax,
    scan_cache: SqlTestScanCache,
) -> tuple[tuple[CompileSqlTestInput, ...], tuple[CompileSqlScenarioInput, ...]]:
    """Attach every SQL test case, then every scenario, saving the scan store afterwards."""

    with record_compile_timing("test_input_compile_ms"):
        tests, scenarios = native_project.attach_sql_tests(
            [_test_file_row(test_file) for test_file in discovered_inputs.test_files],
            [_scenario_row(scenario) for scenario in discovered_inputs.scenario_files],
            {
                "test_input": CompileSqlTestInput,
                "model_payload": CompileModelSqlTestInputPayload,
                "direct_payload": CompileDirectLogicSqlTestInputPayload,
                "test_cte": CompileSqlTestCte,
                "scenario_input": CompileSqlScenarioInput,
                "scenario_cte": CompileSqlScenarioCte,
                "modes": {mode.value: mode for mode in SqlTestMode},
                "test_kind": ResourceKind.TEST,
                "scenario_kind": ResourceKind.SCENARIO,
                "runtime_usage": UsageKind.RUNTIME,
                "render_parameter": _parameter_renderer(value_renderer),
                "adapter_name": value_renderer.adapter_name,
                "text_patterns": sql_test_text,
                "cte_locator": SqlTestCteLocator,
                "scan_store": scan_cache.opened(),
                "scan_key": (SQL_TEST_CTE_SCAN_ALGORITHM, syntax.cache_key),
            },
        )
        scan_cache.save()
    return tuple(tests), tuple(scenarios)


def attach_audits_impl(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
    effective_settings: SettingsConfig,
) -> tuple[tuple[AuditInput, ...], tuple[CompilerDiagnostic, ...]]:
    """Attach every singular audit, then each model's, source's and seed's generic audits."""

    default_severity: object | None = effective_settings.default_audit_severity
    audits, diagnostics = native_project.attach_audits(
        [_audit_file_row(audit_file) for audit_file in discovered_inputs.audit_files],
        {
            "default_severity": None if default_severity is None else str(default_severity),
            "default_run_scope": effective_settings.default_audit_run_scope,
            "builtins": [_audit_file_row(audit_file) for audit_file in builtin_audit_definitions()],
            "declaration_identity": DeclarationIdentity,
            "singular_kind": DeclarationKind.SINGULAR_AUDIT,
            "audit_kind": DeclarationKind.AUDIT,
            "resource_kinds": {kind.value: kind for kind in ResourceKind},
        },
    )
    return tuple(audits), tuple(diagnostics)


def _parameter_renderer(value_renderer: TypedSqlValueRenderer) -> object:
    def render(value: SqlValue) -> tuple[str | None, str | None]:
        try:
            return value_renderer.render_typed_scalar(value=value), None
        except (SqlValueRenderingError, SqlValueValidationError) as error:
            return None, str(error)

    return render


def _test_file_row(test_file: DiscoveredSqlTestFile) -> tuple[object, ...]:
    return (
        str(test_file.file_path),
        str(test_file.relative_path),
        test_file.relative_path.stem,
        test_file,
        test_file.contents,
        [_test_block_row(block) for block in test_file.blocks],
    )


def _test_block_row(block: DiscoveredSqlTestBlock) -> tuple[object, ...]:
    return (
        block,
        block.name,
        block.sql_body,
        block.mode.value,
        [parameter.name for parameter in block.parameters],
        [(case, case.name, list(case.values)) for case in block.cases],
        block.sql_body_span,
    )


def _scenario_row(scenario: DiscoveredSqlScenarioFile) -> tuple[object, ...]:
    return (
        str(scenario.file_path),
        str(scenario.relative_path),
        scenario,
        scenario.contents,
        scenario.sql_body,
        scenario.name,
    )


def _audit_file_row(audit_file: DiscoveredAuditFile) -> tuple[object, ...]:
    return (
        str(audit_file.file_path),
        str(audit_file.relative_path),
        audit_file.file_path.stem,
        audit_file,
        audit_file.declaration_kind is DeclarationKind.AUDIT,
        audit_file.contents,
        [
            (
                block,
                block.name,
                block.sql_body,
                block.evidence_sql,
                block.evaluation_mode == AuditEvaluationMode.MEASUREMENT,
                block.header_values,
            )
            for block in audit_file.blocks
        ],
    )
