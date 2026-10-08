"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.attachments.main._native_test_target_catalog import (
    native_test_target_catalog,
)
from sqlbuild.compiler.compile._helpers.attachment.references import (
    build_known_function_names,
    build_known_ref_names,
    build_known_seed_names,
    build_known_source_names,
    build_known_table_function_names,
    validate_table_function_reference_arities,
)
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import reject_cursor_intrinsics
from sqlbuild.compiler.compile._helpers.render.declarations import (
    declaration_usage_records,
    resolve_declaration_expansion,
    usage_visibility,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    find_macro_call_names,
)
from sqlbuild.compiler.compile._helpers.render.parameters import expand_test_parameters
from sqlbuild.compiler.compile._helpers.render.sql_vars import (
    expand_authored_sql_result,
)
from sqlbuild.compiler.compile._helpers.scenarios.core import extract_sql_scenario_ctes
from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    complete_omitted_ceremonial_select,
    extract_assertion_target_model_names,
)
from sqlbuild.compiler.compile._helpers.sql_tests.extraction_errors import (
    located_extraction_error,
    report_authored_invalid_calls,
)
from sqlbuild.compiler.compile._helpers.sql_tests.helper_ctes import (
    report_test_without_target_model,
    report_unresolvable_test_references,
    sql_test_reads,
)
from sqlbuild.compiler.compile._helpers.sql_tests.native import (
    extract_expanded_sql_tests,
    extract_unexpanded_sql_test,
)
from sqlbuild.compiler.compile.classes.sql_test_scan_cache import SqlTestScanCache
from sqlbuild.compiler.compile.exceptions import CompileInputError, SqlTestExtractionError
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    CompileDirectLogicSqlTestCtes,
    CompileDirectLogicSqlTestInputPayload,
    CompileModelSqlTestCtes,
    CompileModelSqlTestInputPayload,
    CompileSqlFunctionInput,
    CompileSqlReference,
    CompileSqlScenarioCte,
    CompileSqlScenarioCtes,
    CompileSqlScenarioInput,
    CompileSqlTestCtes,
    CompileSqlTestInput,
    DeclarationExpansionContext,
    DeclarationResolutionContext,
    DeclarationScopeResolver,
    LoadedMacro,
    MacroContext,
    SqlReferenceOrigin,
    SqlTestReads,
)
from sqlbuild.compiler.compile.types import (
    SqlTestMode,
)
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredProjectInputs,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestCase,
    DiscoveredSqlTestFile,
    EnumDeclaration,
)
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    ResourceIdentity,
    UsageRecord,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import ResourceKind, ScopeKind, UsageKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


@dataclass(frozen=True)
class _ExpandedSqlTest:
    test_file: DiscoveredSqlTestFile
    test_block: DiscoveredSqlTestBlock
    sql_body: str
    mode: SqlTestMode
    tested_resource_names: tuple[str, ...]
    declaration_usages: tuple[UsageRecord, ...]
    parent_name: str
    test_case: DiscoveredSqlTestCase | None


def build_test_inputs_with_cache(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_vars: dict[str, object],
    macro_context: MacroContext,
    loaded_macros: dict[str, LoadedMacro],
    declaration_expansion: DeclarationExpansionContext,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...],
    sql_lexical_syntax: SqlLexicalSyntax,
    scan_cache: SqlTestScanCache,
) -> tuple[CompileSqlTestInput, ...]:
    """Build SQL test inputs inside the compile timing boundary, then save the scan store."""

    with record_compile_timing("test_input_compile_ms"):
        test_inputs: tuple[CompileSqlTestInput, ...] = build_test_inputs(
            discovered_inputs=discovered_inputs,
            effective_vars=effective_vars,
            macro_context=macro_context,
            loaded_macros=loaded_macros,
            declaration_expansion=declaration_expansion,
            external_sql_reference_resolver=external_sql_reference_resolver,
            sql_function_inputs=sql_function_inputs,
            sql_lexical_syntax=sql_lexical_syntax,
            scan_cache=scan_cache,
        )
        scan_cache.save()
    return test_inputs


def build_test_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_vars: dict[str, object] | None = None,
    macro_context: MacroContext,
    loaded_macros: dict[str, LoadedMacro],
    declaration_expansion: DeclarationExpansionContext,
    sql_lexical_syntax: SqlLexicalSyntax,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...] = (),
    scan_cache: SqlTestScanCache | None = None,
) -> tuple[CompileSqlTestInput, ...]:
    """Build compile-time test inputs from discovered SQL-native test blocks."""

    vars_for_substitution: dict[str, object] = effective_vars or {}
    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    if external_sql_reference_resolver is not None:
        known_model_names.update(
            external_sql_reference_resolver.extend_sql_test_model_names(
                known_model_names=known_model_names
            )
        )
    known_seed_names: set[str] = build_known_seed_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    if external_sql_reference_resolver is not None:
        known_seed_names.update(
            external_sql_reference_resolver.extend_sql_test_seed_names(
                known_seed_names=known_seed_names
            )
        )
        known_source_names.update(
            external_sql_reference_resolver.extend_sql_test_source_names(
                known_source_names=known_source_names
            )
        )
    known_function_names: set[str] = build_known_function_names(discovered_inputs)
    known_table_function_names: set[str] = build_known_table_function_names(discovered_inputs)
    table_function_argument_counts: dict[str, int] = {
        function_input.name: len(function_input.arguments)
        for function_input in sql_function_inputs
        if function_input.return_columns
    }
    test_inputs: list[CompileSqlTestInput] = []
    expanded_tests: list[_ExpandedSqlTest] = []
    resolver: DeclarationScopeResolver | None = declaration_expansion.resolver
    reuse_parent_scope: bool = (
        resolver is not None
        and not any(
            declaration.scope is ScopeKind.PRIVATE
            for declaration in resolver.lookup.index.declarations
        )
        and not any(
            resource.kind is ResourceKind.TEST for resource in resolver.lookup.grants_by_resource
        )
    )
    declarations_by_parent: dict[Path, DeclarationExpansionContext] = {}
    test_file: DiscoveredSqlTestFile
    for test_file in discovered_inputs.test_files:
        test_block: DiscoveredSqlTestBlock
        for test_block in test_file.blocks:
            resource: ResourceIdentity = ResourceIdentity(
                ResourceKind.TEST, test_block.name or test_file.relative_path.stem
            )
            parent: Path = test_file.file_path.parent
            scoped_declarations: DeclarationExpansionContext | None = declarations_by_parent.get(
                parent
            )
            if scoped_declarations is not None:
                scoped_declarations = _project_test_declaration_consumer(
                    context=scoped_declarations, consumer=resource
                )
            else:
                scoped_declarations = resolve_declaration_expansion(
                    context=declaration_expansion,
                    file_path=test_file.file_path,
                    resource=resource,
                )
                if reuse_parent_scope:
                    declarations_by_parent[parent] = scoped_declarations
            case_variants: tuple[DiscoveredSqlTestCase | None, ...] = test_block.cases or (None,)
            test_case: DiscoveredSqlTestCase | None
            for test_case in case_variants:
                parameter_sql: str = test_block.sql_body
                if test_case is not None:
                    parameter_sql, used_parameters = expand_test_parameters(
                        sql=test_block.sql_body,
                        file_path=test_file.file_path,
                        values=test_case.values,
                        value_renderer=scoped_declarations.value_renderer,
                        test_name=test_block.name or test_file.file_path.stem,
                        case_name=test_case.name,
                    )
                    unused_parameters: tuple[str, ...] = tuple(
                        parameter.name
                        for parameter in test_block.parameters
                        if parameter.name not in used_parameters
                    )
                    if unused_parameters:
                        raise CompileInputError(
                            f"SQL test '{test_block.name or test_file.file_path.stem}' declares "
                            f"unused parameters: {', '.join(unused_parameters)} in case "
                            f"'{test_case.name}'",
                            bridge_independent=True,
                        )
                expanded_test_block: DiscoveredSqlTestBlock = (
                    test_block
                    if parameter_sql is test_block.sql_body
                    else replace(test_block, sql_body=parameter_sql)
                )
                test_mode: SqlTestMode = test_block.mode
                tested_resource_names: tuple[str, ...] = ()
                if test_mode in {SqlTestMode.MACRO, SqlTestMode.UDF, SqlTestMode.TABLE_FN}:
                    raw_test_ctes: CompileSqlTestCtes = _validate_raw_direct_logic_test_ctes(
                        sql=expanded_test_block.sql_body,
                        test_block=test_block,
                        test_file=test_file,
                        test_mode=test_mode,
                        syntax=sql_lexical_syntax,
                    )
                    tested_resource_names = _infer_tested_direct_logic_resource_names(
                        raw_test_ctes=raw_test_ctes,
                        test_file=test_file,
                        loaded_macros=loaded_macros,
                        known_function_names=known_function_names,
                        known_table_function_names=known_table_function_names,
                        table_function_argument_counts=table_function_argument_counts,
                        syntax=sql_lexical_syntax,
                    )
                expansion: AuthoredSqlExpansionResult = expand_authored_sql_result(
                    sql=parameter_sql,
                    file_path=test_file.file_path,
                    effective_vars=vars_for_substitution,
                    loaded_macros=loaded_macros,
                    macro_context=macro_context,
                    declarations=(
                        replace(scoped_declarations.declarations, consumer=None)
                        if test_mode is SqlTestMode.MACRO
                        else scoped_declarations.declarations
                    ),
                    declaration_resolver=scoped_declarations.resolver,
                    value_renderer=scoped_declarations.value_renderer,
                    collection_rendering=scoped_declarations.collection_rendering,
                )
                expanded_sql_body: str = complete_omitted_ceremonial_select(
                    sql=expansion.sql,
                    syntax=sql_lexical_syntax,
                )
                reject_cursor_intrinsics(
                    sql=expanded_sql_body,
                    context=f"SQL test '{test_block.name or test_file.file_path.stem}'",
                )
                expanded_tests.append(
                    _ExpandedSqlTest(
                        test_file=test_file,
                        test_block=test_block,
                        sql_body=expanded_sql_body,
                        mode=test_mode,
                        tested_resource_names=tested_resource_names,
                        declaration_usages=(
                            _macro_test_declaration_usages(
                                sql=parameter_sql,
                                resource=resource,
                                declarations=scoped_declarations.declarations,
                            )
                            if test_mode is SqlTestMode.MACRO
                            else expansion.usages
                        ),
                        parent_name=test_block.name or test_file.relative_path.stem,
                        test_case=test_case,
                    )
                )
    try:
        test_ctes_batch: tuple[CompileSqlTestCtes, ...] = extract_expanded_sql_tests(
            tests=tuple(
                (test.sql_body, str(test.test_file.relative_path), test.mode)
                for test in expanded_tests
            ),
            scan_cache=scan_cache,
            syntax=sql_lexical_syntax,
        )
    except SqlTestExtractionError as error:
        failed: _ExpandedSqlTest = expanded_tests[error.test_index]
        raise located_extraction_error(
            error=error,
            test_file=failed.test_file,
            test_block=failed.test_block,
            sql=failed.sql_body,
        ) from None
    target_catalog: _native.SqlTestTargetCatalog | None = (
        native_test_target_catalog(
            models=known_model_names,
            sources=known_source_names,
            seeds=known_seed_names,
            table_functions=known_table_function_names,
            macros=loaded_macros,
        )
        if native_stage_enabled(NativeStage.ATTACHMENTS)
        else None
    )
    for test, test_ctes in zip(expanded_tests, test_ctes_batch, strict=True):
        assertion_target_model_names: tuple[str, ...] = (
            _unmocked_assertion_targets(
                payload=test_ctes.payload, test=test, syntax=sql_lexical_syntax
            )
            if isinstance(test_ctes.payload, CompileModelSqlTestCtes)
            else ()
        )
        validate_test_ctes(
            test_ctes=test_ctes,
            test_file=test.test_file,
            known_model_names=known_model_names,
            known_seed_names=known_seed_names,
            known_source_names=known_source_names,
            known_table_function_names=known_table_function_names,
            loaded_macros=loaded_macros,
            assertion_target_model_names=assertion_target_model_names,
            target_catalog=target_catalog,
        )
        reads: SqlTestReads = SqlTestReads(read_helper_names=(), reference_target_model_names=())
        if isinstance(test_ctes.payload, CompileModelSqlTestCtes):
            if report_unresolvable_test_references(
                payload=test_ctes.payload,
                test_file=test.test_file,
                test_block=test.test_block,
                known_model_names=known_model_names,
                syntax=sql_lexical_syntax,
            ):
                continue
            reads = sql_test_reads(payload=test_ctes.payload, syntax=sql_lexical_syntax)
            if (
                test.mode is SqlTestMode.MODEL
                and not test_ctes.payload.expected_model_names
                and not assertion_target_model_names
                and not reads.reference_target_model_names
            ):
                report_test_without_target_model(
                    payload=test_ctes.payload,
                    test_file=test.test_file,
                    test_block=test.test_block,
                    syntax=sql_lexical_syntax,
                )
                continue
        test_inputs.append(
            CompileSqlTestInput(
                test_file=test.test_file,
                test_block=test.test_block,
                sql_body=test.sql_body,
                mode=test.mode,
                payload=_build_test_input_payload(
                    test_ctes=test_ctes,
                    tested_resource_names=test.tested_resource_names,
                    assertion_target_model_names=assertion_target_model_names,
                    reads=reads,
                ),
                declaration_usages=test.declaration_usages,
                parent_name=test.parent_name,
                case_name=test.test_case.name if test.test_case is not None else None,
                case_index=test.test_case.case_index if test.test_case is not None else None,
                parameter_schema=test.test_block.parameters,
                parameter_values=test.test_case.values if test.test_case is not None else (),
            )
        )
    return tuple(test_inputs)


def _unmocked_assertion_targets(
    *, payload: CompileModelSqlTestCtes, test: _ExpandedSqlTest, syntax: SqlLexicalSyntax
) -> tuple[str, ...]:
    """Return models the assertions call ``__ref()`` on that the test does not mock."""

    targets: tuple[str, ...] = extract_assertion_target_model_names(
        assertion_sql=tuple(cte.sql_body for cte in payload.assertion_ctes),
        syntax=syntax,
        origin=_sql_file_reference_origin(test.test_file),
    )
    return tuple(name for name in targets if name not in payload.mock_model_names)


def _project_test_declaration_consumer(
    *, context: DeclarationExpansionContext, consumer: ResourceIdentity
) -> DeclarationExpansionContext:
    return replace(
        context,
        declarations=replace(context.declarations, consumer=consumer),
    )


def _macro_test_declaration_usages(
    *,
    sql: str,
    resource: ResourceIdentity,
    declarations: DeclarationResolutionContext,
) -> tuple[UsageRecord, ...]:
    usages: tuple[UsageRecord, ...] = declaration_usage_records(
        sql=sql,
        resource=resource,
        declarations=declarations,
    )
    macro_usages: list[UsageRecord] = []
    for name in find_macro_call_names(sql=sql):
        if name not in declarations.macro_records:
            continue
        identity: DeclarationIdentity = declarations.macro_records[name].identity
        visibility: tuple[VisibilityRecord, ...] = declarations.macro_visibility.get(name, ())
        visible_records: tuple[VisibilityRecord, ...] = usage_visibility(
            visibility=visibility, consumer=resource
        )
        if visible_records:
            macro_usages.extend(
                UsageRecord(
                    resource,
                    identity,
                    UsageKind.RUNTIME,
                    through=visible.through,
                )
                for visible in visible_records
            )
        else:
            macro_usages.append(UsageRecord(resource, identity, UsageKind.RUNTIME))
    return tuple(dict.fromkeys((*usages, *macro_usages)))


def _build_test_input_payload(
    *,
    test_ctes: CompileSqlTestCtes,
    tested_resource_names: tuple[str, ...],
    assertion_target_model_names: tuple[str, ...],
    reads: SqlTestReads,
) -> CompileModelSqlTestInputPayload | CompileDirectLogicSqlTestInputPayload:
    match test_ctes.payload:
        case CompileModelSqlTestCtes() as model_payload:
            return CompileModelSqlTestInputPayload(
                authored_ctes=model_payload.authored_ctes,
                macro_mocks=model_payload.macro_mocks,
                mock_model_names=model_payload.mock_model_names,
                mock_source_names=model_payload.mock_source_names,
                mock_seed_names=model_payload.mock_seed_names,
                mock_dbt_ref_names=model_payload.mock_dbt_ref_names,
                mock_table_function_names=model_payload.mock_table_function_names,
                expected_ctes=model_payload.expected_ctes,
                expected_model_names=model_payload.expected_model_names,
                assertion_ctes=model_payload.assertion_ctes,
                assertion_names=model_payload.assertion_names,
                assertion_target_model_names=assertion_target_model_names,
                read_helper_names=reads.read_helper_names,
                reference_target_model_names=reads.reference_target_model_names,
            )
        case CompileDirectLogicSqlTestCtes() as direct_logic_payload:
            return CompileDirectLogicSqlTestInputPayload(
                mode=direct_logic_payload.mode,
                helper_ctes=direct_logic_payload.helper_ctes,
                actual_cte=direct_logic_payload.actual_cte,
                expected_cte=direct_logic_payload.expected_cte,
                tested_resource_names=tested_resource_names,
            )


def _validate_raw_direct_logic_test_ctes(
    *,
    sql: str,
    test_block: DiscoveredSqlTestBlock,
    test_file: DiscoveredSqlTestFile,
    test_mode: SqlTestMode,
    syntax: SqlLexicalSyntax,
) -> CompileSqlTestCtes:
    try:
        test_ctes, invalid_calls = extract_unexpanded_sql_test(
            sql=sql, file_label=str(test_file.relative_path), mode=test_mode, syntax=syntax
        )
    except SqlTestExtractionError as error:
        raise located_extraction_error(
            error=error, test_file=test_file, test_block=test_block, sql=sql
        ) from None
    if not (invalid_calls and isinstance(test_ctes.payload, CompileDirectLogicSqlTestCtes)):
        return test_ctes
    reported: int = report_authored_invalid_calls(
        test_file=test_file,
        test_block=test_block,
        actual_cte_name=test_ctes.payload.actual_cte.name,
        syntax=syntax,
    )
    if reported == 0:
        for cte in (*test_ctes.payload.helper_ctes, test_ctes.payload.expected_cte):
            _ = extract_sql_references(
                sql=cte.sql_body, syntax=syntax, origin=_sql_file_reference_origin(test_file)
            )
    return test_ctes


def _infer_tested_direct_logic_resource_names(
    *,
    raw_test_ctes: CompileSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    loaded_macros: dict[str, LoadedMacro],
    public_enums: dict[str, EnumDeclaration] | None = None,
    public_constants: dict[str, ConstantDeclaration] | None = None,
    known_function_names: set[str],
    known_table_function_names: set[str],
    table_function_argument_counts: dict[str, int],
    syntax: SqlLexicalSyntax,
) -> tuple[str, ...]:
    if not isinstance(raw_test_ctes.payload, CompileDirectLogicSqlTestCtes):
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode '{raw_test_ctes.mode.value}' must "
            "define exactly one actual CTE and exactly one expected CTE",
            bridge_independent=True,
        )
    if raw_test_ctes.mode == SqlTestMode.UDF:
        return _infer_tested_udf_names(
            raw_test_ctes=raw_test_ctes,
            test_file=test_file,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
            syntax=syntax,
        )
    if raw_test_ctes.mode == SqlTestMode.TABLE_FN:
        return _infer_tested_table_function_names(
            raw_test_ctes=raw_test_ctes,
            test_file=test_file,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
            table_function_argument_counts=table_function_argument_counts,
            syntax=syntax,
        )
    tested_macro_names: tuple[str, ...] = find_macro_call_names(
        raw_test_ctes.payload.actual_cte.sql_body
    )
    if not tested_macro_names:
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode 'macro' must call at least one "
            "macro in __macro_actual__",
            bridge_independent=True,
        )
    tested_macro_name: str
    for tested_macro_name in tested_macro_names:
        if tested_macro_name not in loaded_macros:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references unknown macro "
                f"'@{tested_macro_name}'",
                bridge_independent=True,
            )
    return tested_macro_names


def _infer_tested_udf_names(
    *,
    raw_test_ctes: CompileSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    known_function_names: set[str],
    known_table_function_names: set[str],
    syntax: SqlLexicalSyntax,
) -> tuple[str, ...]:
    if not isinstance(raw_test_ctes.payload, CompileDirectLogicSqlTestCtes):
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode 'udf' must define exactly one "
            "__udf_actual__ CTE and exactly one __udf_expected__ CTE",
            bridge_independent=True,
        )
    references: tuple[CompileSqlReference, ...] = extract_sql_references(
        sql=raw_test_ctes.payload.actual_cte.sql_body,
        syntax=syntax,
        origin=_sql_file_reference_origin(test_file),
    )
    tested_udf_names: tuple[str, ...] = tuple(
        dict.fromkeys(
            reference.ref_name
            for reference in references
            if reference.ref_kind == SqlReferenceKind.UDF
        )
    )
    if not tested_udf_names:
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode 'udf' must call at least one "
            "scalar UDF in __udf_actual__",
            bridge_independent=True,
        )
    tested_udf_name: str
    for tested_udf_name in tested_udf_names:
        if tested_udf_name not in known_function_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references unknown SQL function "
                f"'{tested_udf_name}'",
                bridge_independent=True,
            )
        if tested_udf_name in known_table_function_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references table function "
                f"'{tested_udf_name}' with {SqlReferenceKind.UDF.placeholder_call()}; use "
                f"{SqlReferenceKind.TABLE_FUNCTION.placeholder_call()} for table functions",
                bridge_independent=True,
            )
    return tested_udf_names


def _infer_tested_table_function_names(
    *,
    raw_test_ctes: CompileSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    known_function_names: set[str],
    known_table_function_names: set[str],
    table_function_argument_counts: dict[str, int],
    syntax: SqlLexicalSyntax,
) -> tuple[str, ...]:
    if not isinstance(raw_test_ctes.payload, CompileDirectLogicSqlTestCtes):
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode 'table_fn' must define exactly one "
            "__table_fn_actual__ CTE and exactly one __table_fn_expected__ CTE",
            bridge_independent=True,
        )
    references: tuple[CompileSqlReference, ...] = extract_sql_references(
        sql=raw_test_ctes.payload.actual_cte.sql_body,
        syntax=syntax,
        origin=_sql_file_reference_origin(test_file),
    )
    validate_table_function_reference_arities(
        references=references,
        argument_counts=table_function_argument_counts,
        owner=f"SQL test file {test_file.relative_path}",
    )
    tested_table_function_names: tuple[str, ...] = tuple(
        dict.fromkeys(
            reference.ref_name
            for reference in references
            if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION
        )
    )
    if not tested_table_function_names:
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode 'table_fn' must call at least one "
            "table function in __table_fn_actual__",
            bridge_independent=True,
        )
    tested_table_function_name: str
    for tested_table_function_name in tested_table_function_names:
        if tested_table_function_name not in known_function_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references unknown SQL function "
                f"'{tested_table_function_name}'",
                bridge_independent=True,
            )
        if tested_table_function_name not in known_table_function_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references scalar SQL function "
                f"'{tested_table_function_name}' with "
                f"{SqlReferenceKind.TABLE_FUNCTION.placeholder_call()}; use "
                f"{SqlReferenceKind.UDF.placeholder_call()} for scalar UDFs"
            )
    return tested_table_function_names


def build_scenario_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_vars: dict[str, object] | None = None,
    macro_context: MacroContext,
    loaded_macros: dict[str, LoadedMacro],
    declaration_expansion: DeclarationExpansionContext,
    sql_lexical_syntax: SqlLexicalSyntax,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> tuple[CompileSqlScenarioInput, ...]:
    """Build compile-time scenario inputs from discovered SQL-native scenario files."""

    vars_for_substitution: dict[str, object] = effective_vars or {}
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    if external_sql_reference_resolver is not None:
        known_source_names.update(
            external_sql_reference_resolver.extend_sql_test_source_names(
                known_source_names=known_source_names
            )
        )
    scenario_inputs: list[CompileSqlScenarioInput] = []
    source_catalog: _native.SqlTestTargetCatalog | None = (
        native_test_target_catalog(sources=known_source_names)
        if native_stage_enabled(NativeStage.ATTACHMENTS)
        else None
    )
    scenario_file: DiscoveredSqlScenarioFile
    for scenario_file in discovered_inputs.scenario_files:
        resource: ResourceIdentity = ResourceIdentity(ResourceKind.SCENARIO, scenario_file.name)
        scoped_declarations: DeclarationExpansionContext = resolve_declaration_expansion(
            context=declaration_expansion,
            file_path=scenario_file.file_path,
            resource=resource,
        )
        expansion: AuthoredSqlExpansionResult = expand_authored_sql_result(
            sql=scenario_file.sql_body,
            file_path=scenario_file.file_path,
            effective_vars=vars_for_substitution,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
            declarations=scoped_declarations.declarations,
            declaration_resolver=scoped_declarations.resolver,
            value_renderer=scoped_declarations.value_renderer,
            collection_rendering=scoped_declarations.collection_rendering,
        )
        expanded_sql_body: str = complete_omitted_ceremonial_select(
            sql=expansion.sql,
            syntax=sql_lexical_syntax,
        )
        reject_cursor_intrinsics(
            sql=expanded_sql_body,
            context=f"SQL scenario '{scenario_file.file_path.stem}'",
        )
        scenario_ctes: CompileSqlScenarioCtes = extract_sql_scenario_ctes(
            sql=expanded_sql_body,
            file_label=str(scenario_file.relative_path),
            syntax=sql_lexical_syntax,
        )
        _validate_scenario_source_references(
            scenario_ctes=scenario_ctes,
            scenario_file=scenario_file,
            known_source_names=known_source_names,
            syntax=sql_lexical_syntax,
            target_catalog=source_catalog,
        )
        assertion_target_model_names: tuple[str, ...] = extract_assertion_target_model_names(
            assertion_sql=tuple(cte.sql_body for cte in scenario_ctes.assertion_ctes),
            syntax=sql_lexical_syntax,
            origin=_sql_file_reference_origin(scenario_file),
        )
        scenario_inputs.append(
            CompileSqlScenarioInput(
                scenario_file=scenario_file,
                sql_body=expanded_sql_body,
                authored_ctes=scenario_ctes.authored_ctes,
                expected_ctes=scenario_ctes.expected_ctes,
                assertion_ctes=scenario_ctes.assertion_ctes,
                source_fixture_names=scenario_ctes.source_fixture_names,
                ref_fixture_names=scenario_ctes.ref_fixture_names,
                seed_fixture_names=scenario_ctes.seed_fixture_names,
                dbt_ref_fixture_names=scenario_ctes.dbt_ref_fixture_names,
                expected_model_names=scenario_ctes.expected_model_names,
                assertion_names=scenario_ctes.assertion_names,
                assertion_target_model_names=assertion_target_model_names,
                target_model_names=tuple(
                    dict.fromkeys(
                        (*scenario_ctes.expected_model_names, *assertion_target_model_names)
                    )
                ),
                declaration_usages=expansion.usages,
            )
        )
    return tuple(scenario_inputs)


def _sql_file_reference_origin(
    sql_file: DiscoveredSqlTestFile | DiscoveredSqlScenarioFile,
) -> SqlReferenceOrigin:
    return SqlReferenceOrigin(
        file_path=sql_file.file_path,
        relative_path=sql_file.relative_path,
        contents=sql_file.contents,
    )


def _validate_scenario_source_references(
    *,
    scenario_ctes: CompileSqlScenarioCtes,
    scenario_file: DiscoveredSqlScenarioFile,
    known_source_names: set[str],
    syntax: SqlLexicalSyntax,
    target_catalog: _native.SqlTestTargetCatalog | None = None,
) -> None:
    if native_stage_enabled(NativeStage.ATTACHMENTS):
        cte_sources: list[tuple[str, bool, list[str]]]
        extraction_error: CompileInputError | None
        cte_sources, extraction_error = _scenario_cte_sources(
            scenario_ctes=scenario_ctes, scenario_file=scenario_file, syntax=syntax
        )
        error: str | None = (
            target_catalog or native_test_target_catalog(sources=known_source_names)
        ).scenario_source_error(str(scenario_file.relative_path), cte_sources)
        if error is not None:
            raise CompileInputError(error, bridge_independent=True)
        if extraction_error is not None:
            raise extraction_error
        return
    cte: CompileSqlScenarioCte
    for cte in (*scenario_ctes.expected_ctes, *scenario_ctes.assertion_ctes):
        references: tuple[CompileSqlReference, ...] = extract_sql_references(
            sql=cte.sql_body, syntax=syntax, origin=_sql_file_reference_origin(scenario_file)
        )
        reference: CompileSqlReference
        for reference in references:
            if reference.ref_kind != SqlReferenceKind.SOURCE:
                continue
            raise CompileInputError(
                f"SQL scenario file {scenario_file.relative_path} CTE '{cte.name}' must not "
                f"reference project source '{reference.ref_name}' with "
                f"{SqlReferenceKind.SOURCE.placeholder_call()}; source-backed scenario data "
                "is only allowed in helper and fixture CTEs"
            )

    for cte in scenario_ctes.authored_ctes:
        references = extract_sql_references(
            sql=cte.sql_body, syntax=syntax, origin=_sql_file_reference_origin(scenario_file)
        )
        for reference in references:
            if reference.ref_kind != SqlReferenceKind.SOURCE:
                continue
            if reference.ref_name in known_source_names:
                continue
            raise CompileInputError(
                f"SQL scenario file {scenario_file.relative_path} references unknown source "
                f"'{reference.ref_name}'"
            )


def _scenario_cte_sources(
    *,
    scenario_ctes: CompileSqlScenarioCtes,
    scenario_file: DiscoveredSqlScenarioFile,
    syntax: SqlLexicalSyntax,
) -> tuple[list[tuple[str, bool, list[str]]], CompileInputError | None]:
    """Each check-then-fixture CTE's source references, up to the first CTE whose scan raises."""

    checks: tuple[CompileSqlScenarioCte, ...] = (
        *scenario_ctes.expected_ctes,
        *scenario_ctes.assertion_ctes,
    )
    cte_sources: list[tuple[str, bool, list[str]]] = []
    for position, cte in enumerate((*checks, *scenario_ctes.authored_ctes)):
        try:
            references: tuple[CompileSqlReference, ...] = extract_sql_references(
                sql=cte.sql_body, syntax=syntax, origin=_sql_file_reference_origin(scenario_file)
            )
        except CompileInputError as error:
            return cte_sources, error
        cte_sources.append(
            (
                cte.name,
                position < len(checks),
                [
                    reference.ref_name
                    for reference in references
                    if reference.ref_kind == SqlReferenceKind.SOURCE
                ],
            )
        )
    return cte_sources, None


def validate_test_ctes(
    *,
    test_ctes: CompileSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    known_model_names: set[str],
    known_seed_names: set[str],
    known_source_names: set[str],
    known_table_function_names: set[str],
    loaded_macros: dict[str, LoadedMacro],
    assertion_target_model_names: tuple[str, ...],
    target_catalog: _native.SqlTestTargetCatalog | None = None,
) -> None:
    """Validate SQL-native test CTE targets; preview reuses one native catalog per compile."""

    if isinstance(test_ctes.payload, CompileDirectLogicSqlTestCtes):
        return

    model_payload: CompileModelSqlTestCtes = test_ctes.payload
    if native_stage_enabled(NativeStage.ATTACHMENTS):
        catalog: _native.SqlTestTargetCatalog = target_catalog or native_test_target_catalog(
            models=known_model_names,
            sources=known_source_names,
            seeds=known_seed_names,
            table_functions=known_table_function_names,
            macros=loaded_macros,
        )
        error: str | None = catalog.unknown_test_target(
            str(test_file.relative_path),
            (
                [*model_payload.mock_model_names],
                [*model_payload.mock_source_names],
                [*model_payload.mock_seed_names],
                [*model_payload.mock_table_function_names],
                [*model_payload.macro_mocks],
                [*model_payload.expected_model_names],
                [*assertion_target_model_names],
            ),
        )
        if error is not None:
            raise CompileInputError(error, bridge_independent=True)
        return

    mock_model_name: str
    for mock_model_name in model_payload.mock_model_names:
        if mock_model_name not in known_model_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} mocks unknown model '{mock_model_name}'"
            )
    mock_source_name: str
    for mock_source_name in model_payload.mock_source_names:
        if mock_source_name not in known_source_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} mocks unknown source '{mock_source_name}'"
            )
    mock_seed_name: str
    for mock_seed_name in model_payload.mock_seed_names:
        if mock_seed_name not in known_seed_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} mocks unknown seed '{mock_seed_name}'"
            )
    mock_table_function_name: str
    for mock_table_function_name in model_payload.mock_table_function_names:
        if mock_table_function_name not in known_table_function_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} mocks unknown table function "
                f"'{mock_table_function_name}'"
            )
    macro_mock_name: str
    for macro_mock_name in model_payload.macro_mocks:
        if macro_mock_name not in loaded_macros:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} mocks unknown macro '{macro_mock_name}'"
            )
    expected_model_name: str
    for expected_model_name in model_payload.expected_model_names:
        if expected_model_name not in known_model_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} expects unknown model "
                f"'{expected_model_name}'"
            )

    assertion_target_name: str
    for assertion_target_name in assertion_target_model_names:
        if assertion_target_name not in known_model_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} assertion references unknown model "
                f"'{assertion_target_name}'"
            )
