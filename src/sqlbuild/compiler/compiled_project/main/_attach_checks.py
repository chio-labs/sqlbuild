"""SQL tests, scenarios and audits attached natively and held by the compile's native project."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.classes.sql_test_scan_cache import SqlTestScanCache
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    CompileSqlScenarioInput,
    CompileSqlTestInput,
)
from sqlbuild.compiler.compile.types import AuditInput, SourceInput, TypedSqlValueRenderer
from sqlbuild.compiler.compiled_project._helpers.assurance_attachment import (
    attach_audits_impl,
    attach_sql_tests_impl,
    resource_diagnostics_impl,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import SettingsConfig


def attach_checks(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
    settings: tuple[SettingsConfig, TypedSqlValueRenderer, SqlLexicalSyntax],
    scan_cache: SqlTestScanCache,
    source_inputs: tuple[SourceInput, ...],
) -> tuple[
    tuple[CompileSqlTestInput, ...],
    tuple[CompileSqlScenarioInput, ...],
    tuple[AuditInput, ...],
    tuple[CompilerDiagnostic, ...],
]:
    """Attach every SQL test case, scenario and audit, then report every resource diagnostic."""

    effective_settings, value_renderer, syntax = settings
    tests, scenarios = attach_sql_tests_impl(
        discovered_inputs=discovered_inputs,
        native_project=native_project,
        value_renderer=value_renderer,
        syntax=syntax,
        scan_cache=scan_cache,
    )
    audits, diagnostics = attach_audits_impl(
        discovered_inputs=discovered_inputs,
        native_project=native_project,
        effective_settings=effective_settings,
    )
    return (
        tests,
        scenarios,
        audits,
        (
            *diagnostics,
            *resource_diagnostics_impl(
                discovered_inputs=discovered_inputs,
                native_project=native_project,
                source_inputs=source_inputs,
            ),
        ),
    )
