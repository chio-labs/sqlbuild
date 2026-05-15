from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompileSqlReference,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, SqlTestMode
from sqlbuild.compiler.lineage.types import InferredNullability


@dataclass(frozen=True)
class ExpandSqlMacrosTestCase:
    description: str
    macro_file_contents: str
    sql: str
    expected_sql: str
    macro_overrides: dict[str, str] = field(default_factory=dict)


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
    expected_mock_seed_names: tuple[str, ...] = ()
    expected_mock_dbt_ref_names: tuple[str, ...] = ()
    expected_assertion_names: tuple[str, ...] = ()
    expected_macro_mocks: dict[str, str] = field(default_factory=dict)
    mode: SqlTestMode = SqlTestMode.MODEL
    expected_macro_actual_cte_name: str | None = None
    expected_macro_expected_cte_name: str | None = None


@dataclass(frozen=True)
class ExtractSqlTestCtesErrorTestCase:
    description: str
    sql: str
    expected_error_fragment: str
    mode: SqlTestMode = SqlTestMode.MODEL


@dataclass(frozen=True)
class ExtractSqlScenarioCtesTestCase:
    description: str
    sql: str
    expected_authored_cte_names: tuple[str, ...]
    expected_source_fixture_names: tuple[str, ...]
    expected_ref_fixture_names: tuple[str, ...]
    expected_expected_model_names: tuple[str, ...]
    expected_assertion_names: tuple[str, ...]
    expected_seed_fixture_names: tuple[str, ...] = ()
    expected_dbt_ref_fixture_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractSqlScenarioCtesErrorTestCase:
    description: str
    sql: str
    expected_error_fragment: str


@dataclass(frozen=True)
class BuildScenarioInputsTestCase:
    description: str
    sql_body: str
    effective_vars: dict[str, object]
    expected_source_fixture_names: tuple[str, ...]
    expected_ref_fixture_names: tuple[str, ...]
    expected_seed_fixture_names: tuple[str, ...]
    expected_expected_model_names: tuple[str, ...]
    expected_assertion_names: tuple[str, ...]
    expected_sql_fragment: str
    expected_dbt_ref_fixture_names: tuple[str, ...] = ()


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
    seed_names: frozenset[str] = field(default_factory=frozenset)


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
    expected_model_macro_deps: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    expected_test_modes: tuple[str, ...] = field(default_factory=tuple)
    expected_tested_macro_names: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    expected_seed_target_schemas: tuple[str | None, ...] = field(default_factory=tuple)
    expected_seed_target_databases: tuple[str | None, ...] = field(default_factory=tuple)
    expected_seed_target_qualified_names: tuple[str | None, ...] = field(default_factory=tuple)
    expected_audit_attached_target_kinds: tuple[AttachedAuditTargetKind | None, ...] = ()


@dataclass(frozen=True)
class InferColumnsTestCase:
    description: str
    query_sql: str
    expected_columns: tuple[InferredColumn, ...] | None
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] = field(
        default_factory=dict
    )
    inference_profile: ExpressionInferenceProfile | None = None


@dataclass(frozen=True)
class ValidateSqlSyntaxTestCase:
    description: str
    query_sql: str
    expected_valid: bool
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class IncrementalConfigValidTestCase:
    description: str
    config_values: dict[str, object]
    ref_count: int
    expected_valid: bool = True


@dataclass(frozen=True)
class IncrementalConfigErrorTestCase:
    description: str
    config_values: dict[str, object]
    ref_count: int
    expected_error_fragment: str


@dataclass(frozen=True)
class SubstituteSqlVarsTestCase:
    description: str
    sql: str
    effective_vars: dict[str, object]
    expected_sql: str
    environment_variables: dict[str, str] = field(default_factory=dict)
    context_values: dict[str, str | None] | None = None


@dataclass(frozen=True)
class SubstituteSqlVarsErrorTestCase:
    description: str
    sql: str
    effective_vars: dict[str, object]
    expected_error_fragment: str
    context_values: dict[str, str | None] | None = None


@dataclass(frozen=True)
class ExpandTemplateDataTestCase:
    description: str
    value: object
    variables: dict[str, object]
    context_values: dict[str, str | None]
    context_label: str
    allow_context: bool
    preserve_context_tokens: bool
    preserve_unknown_context: bool
    expected_value: object


@dataclass(frozen=True)
class ExpandTemplateDataErrorTestCase:
    description: str
    value: object
    variables: dict[str, object]
    context_values: dict[str, str | None]
    context_label: str
    allow_context: bool
    preserve_context_tokens: bool
    preserve_unknown_context: bool
    expected_error_fragment: str


@dataclass(frozen=True)
class VarMacroCollisionTestCase:
    description: str
    var_names: tuple[str, ...]
    macro_names: tuple[str, ...]
    expected_valid: bool
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class NonIncrementalConfigValidTestCase:
    description: str
    config_values: dict[str, object]
    expected_valid: bool = True


@dataclass(frozen=True)
class NonIncrementalConfigErrorTestCase:
    description: str
    config_values: dict[str, object]
    expected_error_fragment: str


@dataclass(frozen=True)
class ResolveAuditSeverityTestCase:
    description: str
    instance_severity: str | None
    default_severity: str | None
    expected_severity: str | None = None
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ResolveAuditRunScopeTestCase:
    description: str
    instance_run_scope: str | None
    default_run_scope: str | None
    expected_run_scope: str


@dataclass(frozen=True)
class ResolveAuditRunScopeErrorTestCase:
    description: str
    instance_run_scope: str | None
    default_run_scope: str | None
    expected_error_fragment: str


@dataclass(frozen=True)
class ValidateModelAttachedAuditRefsTestCase:
    description: str
    references: tuple[CompileSqlReference, ...]
    attached_target_kind: str
    attached_target_name: str
    expected_valid: bool = True
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class ValidateAuditRefsErrorTestCase:
    description: str
    references: tuple[CompileSqlReference, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class CustomMaterializationConfigErrorTestCase:
    description: str
    config_values: dict[str, object]
    custom_materialization_names: frozenset[str]
    expected_error_fragment: str


@dataclass(frozen=True)
class CustomMaterializationConfigValidTestCase:
    description: str
    config_values: dict[str, object]
    custom_materialization_names: frozenset[str]
    expected_valid: bool = True


@dataclass(frozen=True)
class PlaceholderConfigErrorTestCase:
    description: str
    config_values: dict[str, object]
    query_sql: str
    custom_materialization_names: frozenset[str]
    expected_error_fragment: str


@dataclass(frozen=True)
class PlaceholderConfigValidTestCase:
    description: str
    config_values: dict[str, object]
    query_sql: str
    custom_materialization_names: frozenset[str]
    expected_valid: bool = True


@dataclass(frozen=True)
class SubstitutePlaceholderDefaultsTestCase:
    description: str
    query_sql: str
    placeholders: dict[str, str]
    expected_sql: str
