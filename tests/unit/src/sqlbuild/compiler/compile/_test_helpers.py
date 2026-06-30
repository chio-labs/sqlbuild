from pathlib import Path

from sqlbuild.compiler.compile.models.sql_tests import (
    CompileModelSqlTestInputPayload,
    CompileSqlTestInput,
)
from sqlbuild.integrations.dbt.main.api.build_compile_reference_resolver import (
    build_compile_reference_resolver,
)
from sqlbuild.shared.types import ExternalSqlReferenceResolver


def base_repo_files() -> dict[str, str]:
    return {
        "sqlbuild_project.toml": (
            'name = "demo"\nadapter = "duckdb"\n\n[settings]\ndefault_audit_severity = "warn"\n'
        ),
    }


def build_external_sql_reference_resolver(
    *, project_dir: Path
) -> ExternalSqlReferenceResolver | None:
    manifest_path: Path = project_dir / "dbt" / "target" / "manifest.json"
    if not manifest_path.is_file():
        return None
    return build_compile_reference_resolver(
        manifest_contents=manifest_path.read_text(encoding="utf-8")
    )


def expected_or_actual[T](expected: T | None, actual: T) -> T:
    if expected is None:
        return actual
    return expected


def compile_sql_test_authored_cte_names(test_input: CompileSqlTestInput) -> tuple[str, ...]:
    if not isinstance(test_input.payload, CompileModelSqlTestInputPayload):
        return ()
    return tuple(cte.name for cte in test_input.payload.authored_ctes)


def compile_sql_test_mock_model_names(test_input: CompileSqlTestInput) -> tuple[str, ...]:
    if not isinstance(test_input.payload, CompileModelSqlTestInputPayload):
        return ()
    return test_input.payload.mock_model_names


def compile_sql_test_mock_source_names(test_input: CompileSqlTestInput) -> tuple[str, ...]:
    if not isinstance(test_input.payload, CompileModelSqlTestInputPayload):
        return ()
    return test_input.payload.mock_source_names


def compile_sql_test_mock_seed_names(test_input: CompileSqlTestInput) -> tuple[str, ...]:
    if not isinstance(test_input.payload, CompileModelSqlTestInputPayload):
        return ()
    return test_input.payload.mock_seed_names


def compile_sql_test_expected_model_names(test_input: CompileSqlTestInput) -> tuple[str, ...]:
    if not isinstance(test_input.payload, CompileModelSqlTestInputPayload):
        return ()
    return test_input.payload.expected_model_names
