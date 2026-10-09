"""Compiled SQL tests built from the facts the native assembly returns."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import SQL_TEST_HELPER_REFERENCE_CODE
from sqlbuild.compiler.compile.models import (
    CompiledDirectLogicSqlTestPayload,
    CompileDirectLogicSqlTestInputPayload,
    CompiledModelSqlTestPayload,
    CompiledObjectKey,
    CompiledSqlTest,
    CompiledSqlTestResource,
    CompilerDiagnostic,
    CompileSqlTestInput,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.sql_test_glue.models import NativeSqlTestAssembly
from sqlbuild.compiler.sql_test_glue.types import (
    NativeSqlTestDiagnosticRow,
    NativeSqlTestFactsRow,
)
from sqlbuild.spec.contracts.models import SourceLocation


def native_sql_test_assembly(
    *, test_input: CompileSqlTestInput, facts: NativeSqlTestFactsRow
) -> NativeSqlTestAssembly:
    """The compiled test `_assemble_compiled_sql_test` builds, from natively assembled facts."""

    name, scope_dep_rows, target_model_names, case_fingerprint, resource_name, diagnostics = facts
    scope_deps: tuple[CompiledObjectKey, ...] = tuple(
        CompiledObjectKey(resource_type=resource_type, name=dep_name)
        for resource_type, dep_name in scope_dep_rows
    )
    payload = test_input.payload
    compiled_payload: CompiledModelSqlTestPayload | CompiledDirectLogicSqlTestPayload
    tested_resources: tuple[CompiledSqlTestResource, ...] = ()
    expected_model_names: tuple[str, ...] = ()
    assertion_names: tuple[str, ...] = ()
    assertion_target_model_names: tuple[str, ...] = ()
    read_helper_names: tuple[str, ...] = ()
    reference_target_model_names: tuple[str, ...] = ()
    if isinstance(payload, CompileDirectLogicSqlTestInputPayload):
        compiled_payload = CompiledDirectLogicSqlTestPayload(
            mode=payload.mode,
            helper_ctes=payload.helper_ctes,
            actual_cte=payload.actual_cte,
            expected_cte=payload.expected_cte,
            tested_resource_names=payload.tested_resource_names,
        )
        tested_resources = tuple(
            CompiledSqlTestResource(kind=payload.mode, name=resource_name)
            for resource_name in payload.tested_resource_names
        )
    else:
        compiled_payload = CompiledModelSqlTestPayload(
            authored_ctes=payload.authored_ctes,
            macro_mocks=payload.macro_mocks,
            model_query_overrides={},
            mock_model_names=payload.mock_model_names,
            mock_source_names=payload.mock_source_names,
            mock_seed_names=payload.mock_seed_names,
            mock_dbt_ref_names=payload.mock_dbt_ref_names,
            mock_table_function_names=payload.mock_table_function_names,
            expected_ctes=payload.expected_ctes,
            expected_model_names=payload.expected_model_names,
            assertion_ctes=payload.assertion_ctes,
            assertion_names=payload.assertion_names,
        )
        expected_model_names = payload.expected_model_names
        assertion_names = payload.assertion_names
        assertion_target_model_names = payload.assertion_target_model_names
        read_helper_names = payload.read_helper_names
        reference_target_model_names = payload.reference_target_model_names
    return NativeSqlTestAssembly(
        test=CompiledSqlTest(
            key=CompiledObjectKey(resource_type=CompiledResourceType.SQL_TEST, name=name),
            scope_deps=scope_deps,
            name=name,
            test_file=test_input.test_file,
            test_block=test_input.test_block,
            sql_body=test_input.sql_body,
            mode=test_input.mode,
            payload=compiled_payload,
            source_path=test_input.test_file.relative_path,
            ownership_root=test_input.test_file.ownership_root,
            block_index=test_input.test_block.test_index,
            explicit_name=test_input.test_block.name,
            parent_name=test_input.parent_name,
            case_name=test_input.case_name,
            case_index=test_input.case_index,
            case_fingerprint=case_fingerprint,
            parameter_schema=test_input.parameter_schema,
            parameter_values=test_input.parameter_values,
            expected_model_names=expected_model_names,
            assertion_names=assertion_names,
            assertion_target_model_names=assertion_target_model_names,
            read_helper_names=read_helper_names,
            reference_target_model_names=reference_target_model_names,
            target_model_names=tuple(target_model_names),
            tested_resources=tested_resources,
        ),
        diagnostics=tuple(
            _keyed_diagnostic(test_input=test_input, resource_name=resource_name, row=row)
            for row in diagnostics
        ),
    )


def _keyed_diagnostic(
    *, test_input: CompileSqlTestInput, resource_name: str, row: NativeSqlTestDiagnosticRow
) -> tuple[tuple[str, ...], CompilerDiagnostic]:
    line, column, end_line, end_column, message, help_text = row
    path = test_input.test_file.relative_path
    return (
        (SQL_TEST_HELPER_REFERENCE_CODE, path.as_posix(), f"{line:09d}:{column:09d}", message),
        CompilerDiagnostic(
            phase=DiagnosticPhase.COMPILE,
            severity=DiagnosticSeverity.ERROR,
            code=SQL_TEST_HELPER_REFERENCE_CODE,
            message=message,
            resource_type=CompiledResourceType.SQL_TEST,
            resource_name=resource_name,
            location=SourceLocation(
                path=path, line=line, column=column, end_line=end_line, end_column=end_column
            ),
            help=help_text,
        ),
    )
