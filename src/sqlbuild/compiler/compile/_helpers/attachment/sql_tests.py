"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import re
from dataclasses import replace

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
    extract_assertion_target_model_names,
    extract_sql_test_ctes,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
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
    LoadedMacro,
    MacroContext,
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
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.compiler.scopes.models import ResourceIdentity
from sqlbuild.compiler.scopes.types import ResourceKind

_HOOK_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{[^}]+\}")
_LEGACY_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hook", "post_hook"})
_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_HOOK_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset(
    {"ctx", "context", "_ctx", "hook_context"}
)


def build_test_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_vars: dict[str, object] | None = None,
    macro_context: MacroContext,
    loaded_macros: dict[str, LoadedMacro],
    declaration_expansion: DeclarationExpansionContext,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...] = (),
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
    test_file: DiscoveredSqlTestFile
    for test_file in discovered_inputs.test_files:
        test_block: DiscoveredSqlTestBlock
        for test_block in test_file.blocks:
            resource: ResourceIdentity = ResourceIdentity(
                ResourceKind.TEST, test_block.name or test_file.relative_path.stem
            )
            scoped_declarations: DeclarationExpansionContext = resolve_declaration_expansion(
                context=declaration_expansion,
                file_path=test_file.file_path,
                resource=resource,
            )
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
                            f"'{test_case.name}'"
                        )
                expanded_test_block: DiscoveredSqlTestBlock = replace(
                    test_block,
                    sql_body=parameter_sql,
                )
                test_mode: SqlTestMode = test_block.mode
                tested_resource_names: tuple[str, ...] = ()
                if test_mode in {SqlTestMode.MACRO, SqlTestMode.UDF, SqlTestMode.TABLE_FN}:
                    raw_test_ctes: CompileSqlTestCtes = _validate_raw_direct_logic_test_ctes(
                        test_block=expanded_test_block,
                        test_file=test_file,
                        test_mode=test_mode,
                    )
                    tested_resource_names = _infer_tested_direct_logic_resource_names(
                        raw_test_ctes=raw_test_ctes,
                        test_file=test_file,
                        loaded_macros=loaded_macros,
                        known_function_names=known_function_names,
                        known_table_function_names=known_table_function_names,
                        table_function_argument_counts=table_function_argument_counts,
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
                expanded_sql_body: str = expansion.sql
                reject_cursor_intrinsics(
                    sql=expanded_sql_body,
                    context=f"SQL test '{test_block.name or test_file.file_path.stem}'",
                )
                test_ctes: CompileSqlTestCtes = extract_sql_test_ctes(
                    sql=expanded_sql_body,
                    file_label=str(test_file.relative_path),
                    mode=test_mode,
                )
                validate_test_ctes(
                    test_ctes=test_ctes,
                    test_file=test_file,
                    known_model_names=known_model_names,
                    known_seed_names=known_seed_names,
                    known_source_names=known_source_names,
                    loaded_macros=loaded_macros,
                )
                test_payload: (
                    CompileModelSqlTestInputPayload | CompileDirectLogicSqlTestInputPayload
                ) = _build_test_input_payload(
                    test_ctes=test_ctes,
                    tested_resource_names=tested_resource_names,
                )
                test_inputs.append(
                    CompileSqlTestInput(
                        test_file=test_file,
                        test_block=test_block,
                        sql_body=expanded_sql_body,
                        mode=test_mode,
                        payload=test_payload,
                        declaration_usages=(
                            declaration_usage_records(
                                sql=parameter_sql,
                                resource=resource,
                                declarations=scoped_declarations.declarations,
                            )
                            if test_mode is SqlTestMode.MACRO
                            else expansion.usages
                        ),
                        parent_name=test_block.name or test_file.relative_path.stem,
                        case_name=test_case.name if test_case is not None else None,
                        case_index=test_case.case_index if test_case is not None else None,
                        parameter_schema=test_block.parameters,
                        parameter_values=test_case.values if test_case is not None else (),
                    )
                )
    return tuple(test_inputs)


def _build_test_input_payload(
    *, test_ctes: CompileSqlTestCtes, tested_resource_names: tuple[str, ...]
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
                expected_model_names=model_payload.expected_model_names,
                assertion_ctes=model_payload.assertion_ctes,
                assertion_names=model_payload.assertion_names,
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
    test_block: DiscoveredSqlTestBlock,
    test_file: DiscoveredSqlTestFile,
    test_mode: SqlTestMode,
) -> CompileSqlTestCtes:
    return extract_sql_test_ctes(
        sql=test_block.sql_body,
        file_label=str(test_file.relative_path),
        mode=test_mode,
    )


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
) -> tuple[str, ...]:
    if not isinstance(raw_test_ctes.payload, CompileDirectLogicSqlTestCtes):
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode '{raw_test_ctes.mode.value}' must "
            "define exactly one actual CTE and exactly one expected CTE"
        )
    if raw_test_ctes.mode == SqlTestMode.UDF:
        return _infer_tested_udf_names(
            raw_test_ctes=raw_test_ctes,
            test_file=test_file,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
        )
    if raw_test_ctes.mode == SqlTestMode.TABLE_FN:
        return _infer_tested_table_function_names(
            raw_test_ctes=raw_test_ctes,
            test_file=test_file,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
            table_function_argument_counts=table_function_argument_counts,
        )
    tested_macro_names: tuple[str, ...] = find_macro_call_names(
        raw_test_ctes.payload.actual_cte.sql_body
    )
    if not tested_macro_names:
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode 'macro' must call at least one "
            "macro in __macro_actual__"
        )
    tested_macro_name: str
    for tested_macro_name in tested_macro_names:
        if tested_macro_name not in loaded_macros:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references unknown macro "
                f"'@{tested_macro_name}'"
            )
    return tested_macro_names


def _infer_tested_udf_names(
    *,
    raw_test_ctes: CompileSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    known_function_names: set[str],
    known_table_function_names: set[str],
) -> tuple[str, ...]:
    if not isinstance(raw_test_ctes.payload, CompileDirectLogicSqlTestCtes):
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode 'udf' must define exactly one "
            "__udf_actual__ CTE and exactly one __udf_expected__ CTE"
        )
    references: tuple[CompileSqlReference, ...] = extract_sql_references(
        raw_test_ctes.payload.actual_cte.sql_body
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
            "scalar UDF in __udf_actual__"
        )
    tested_udf_name: str
    for tested_udf_name in tested_udf_names:
        if tested_udf_name not in known_function_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references unknown SQL function "
                f"'{tested_udf_name}'"
            )
        if tested_udf_name in known_table_function_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references table function "
                f"'{tested_udf_name}' with {SqlReferenceKind.UDF.placeholder_call()}; use "
                f"{SqlReferenceKind.TABLE_FUNCTION.placeholder_call()} for table functions"
            )
    return tested_udf_names


def _infer_tested_table_function_names(
    *,
    raw_test_ctes: CompileSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    known_function_names: set[str],
    known_table_function_names: set[str],
    table_function_argument_counts: dict[str, int],
) -> tuple[str, ...]:
    if not isinstance(raw_test_ctes.payload, CompileDirectLogicSqlTestCtes):
        raise CompileInputError(
            f"SQL test file {test_file.relative_path} mode 'table_fn' must define exactly one "
            "__table_fn_actual__ CTE and exactly one __table_fn_expected__ CTE"
        )
    references: tuple[CompileSqlReference, ...] = extract_sql_references(
        raw_test_ctes.payload.actual_cte.sql_body
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
            "table function in __table_fn_actual__"
        )
    tested_table_function_name: str
    for tested_table_function_name in tested_table_function_names:
        if tested_table_function_name not in known_function_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} references unknown SQL function "
                f"'{tested_table_function_name}'"
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
        expanded_sql_body: str = expansion.sql
        reject_cursor_intrinsics(
            sql=expanded_sql_body,
            context=f"SQL scenario '{scenario_file.file_path.stem}'",
        )
        scenario_ctes: CompileSqlScenarioCtes = extract_sql_scenario_ctes(
            sql=expanded_sql_body,
            file_label=str(scenario_file.relative_path),
        )
        _validate_scenario_source_references(
            scenario_ctes=scenario_ctes,
            scenario_file=scenario_file,
            known_source_names=known_source_names,
        )
        assertion_target_model_names: tuple[str, ...] = extract_assertion_target_model_names(
            assertion_sql=tuple(cte.sql_body for cte in scenario_ctes.assertion_ctes)
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


def _validate_scenario_source_references(
    *,
    scenario_ctes: CompileSqlScenarioCtes,
    scenario_file: DiscoveredSqlScenarioFile,
    known_source_names: set[str],
) -> None:
    cte: CompileSqlScenarioCte
    for cte in (*scenario_ctes.expected_ctes, *scenario_ctes.assertion_ctes):
        references: tuple[CompileSqlReference, ...] = extract_sql_references(cte.sql_body)
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
        references = extract_sql_references(cte.sql_body)
        for reference in references:
            if reference.ref_kind != SqlReferenceKind.SOURCE:
                continue
            if reference.ref_name in known_source_names:
                continue
            raise CompileInputError(
                f"SQL scenario file {scenario_file.relative_path} references unknown source "
                f"'{reference.ref_name}'"
            )


def validate_test_ctes(
    *,
    test_ctes: CompileSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    known_model_names: set[str],
    known_seed_names: set[str],
    known_source_names: set[str],
    loaded_macros: dict[str, LoadedMacro],
) -> None:
    """Validate SQL-native test CTE targets against discovered inputs."""

    if isinstance(test_ctes.payload, CompileDirectLogicSqlTestCtes):
        return

    model_payload: CompileModelSqlTestCtes = test_ctes.payload

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
    for assertion_target_name in extract_assertion_target_model_names(
        assertion_sql=tuple(cte.sql_body for cte in model_payload.assertion_ctes)
    ):
        if assertion_target_name not in known_model_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} assertion references unknown model "
                f"'{assertion_target_name}'"
            )
