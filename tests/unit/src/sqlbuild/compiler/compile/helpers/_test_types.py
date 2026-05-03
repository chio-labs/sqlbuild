from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompileSqlReference, InferredColumn
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind


@dataclass(frozen=True)
class ExpandSqlMacrosTestCase:
    description: str
    macro_file_contents: str
    sql: str
    expected_sql: str


@dataclass(frozen=True)
class ExpandSqlMacrosErrorTestCase:
    description: str
    macro_file_contents: str
    sql: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ExtractSqlTestCtesTestCase:
    description: str
    sql: str
    expected_authored_cte_names: tuple[str, ...]
    expected_mock_model_names: tuple[str, ...]
    expected_mock_source_names: tuple[str, ...]
    expected_expected_model_names: tuple[str, ...]


@dataclass(frozen=True)
class ExtractSqlTestCtesErrorTestCase:
    description: str
    sql: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ExtractSqlglotExpectedBranchesTestCase:
    description: str
    sql: str
    expected_branch_column_names: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class ExtractSqlglotExpectedBranchesErrorTestCase:
    description: str
    sql: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ModelBuildDepsTestCase:
    description: str
    references: tuple[CompileSqlReference, ...]
    expected_deps: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class AuditScopeDepsTestCase:
    description: str
    references: tuple[CompileSqlReference, ...]
    attached_target_kind: str | None
    attached_target_name: str | None
    expected_scope_deps: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class SqlTestScopeDepsTestCase:
    description: str
    expected_model_names: tuple[str, ...]
    expected_scope_deps: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class AssembleCompiledProjectTestCase:
    description: str
    repo_files: dict[str, str]
    expected_model_names: tuple[str, ...]
    expected_model_deps: tuple[tuple[CompiledObjectKey, ...], ...]
    expected_model_target_names: tuple[str, ...]
    expected_model_target_schemas: tuple[str | None, ...]
    expected_source_names: tuple[str, ...]
    expected_seed_names: tuple[str, ...]
    expected_audit_names: tuple[str, ...]
    expected_audit_scope_deps: tuple[tuple[CompiledObjectKey, ...], ...]
    expected_test_names: tuple[str, ...]
    expected_test_scope_deps: tuple[tuple[CompiledObjectKey, ...], ...]
    expected_test_expected_model_names: tuple[tuple[str, ...], ...]
    expected_audit_attached_target_kinds: tuple[AttachedAuditTargetKind | None, ...] = ()


@dataclass(frozen=True)
class InferColumnsTestCase:
    description: str
    query_sql: str
    expected_columns: tuple[InferredColumn, ...] | None
