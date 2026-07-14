from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    LoadedMacro,
)
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput


@dataclass(frozen=True)
class ManifestTopLevelTestCase:
    description: str
    project: CompiledProject
    plan_output: PlanOutput
    loaded_macros: dict[str, LoadedMacro]
    project_name: str
    adapter_type: str
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_node_count: int
    expected_source_count: int
    expected_macro_count: int
    expected_metadata_project_name: str
    expected_metadata_adapter_type: str
    expected_metadata_schema_version: str


@dataclass(frozen=True)
class ManifestModelNodeTestCase:
    description: str
    model: CompiledModel
    plan_entries: tuple[ModelPlanEntry, ...]
    project_name: str
    expected_unique_id: str
    expected_resource_type: str
    expected_database: str | None
    expected_schema: str | None
    expected_alias: str
    expected_fqn: list[str]
    expected_raw_code: str
    expected_compiled_code: str
    expected_relation_name: str | None
    expected_description: str
    expected_materialized: str
    expected_checksum_name: str
    expected_column_names: tuple[str, ...] = ()
    expected_column_types: dict[str, str | None] = field(default_factory=dict)
    expected_depends_on_nodes: tuple[str, ...] = ()
    expected_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ManifestSourceNodeTestCase:
    description: str
    project_name: str
    expected_unique_id: str
    expected_resource_type: str
    expected_database: str | None
    expected_schema: str
    expected_identifier: str
    expected_description: str
    expected_source_name: str
    expected_column_names: tuple[str, ...] = ()
    expected_column_types: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class ManifestSeedNodeTestCase:
    description: str
    project_name: str
    expected_unique_id: str
    expected_resource_type: str
    expected_materialized: str


@dataclass(frozen=True)
class ManifestMacroNodeTestCase:
    description: str
    project_name: str
    expected_unique_id: str
    expected_name: str
    expected_resource_type: str
    expected_macro_sql: str
    expected_path: str


@dataclass(frozen=True)
class ManifestParentMapTestCase:
    description: str
    project_name: str
    expected_parent_entry: tuple[str, list[str]]
    expected_child_entry: tuple[str, list[str]]


@dataclass(frozen=True)
class ManifestAuditNodeTestCase:
    description: str
    project_name: str
    expected_unique_id: str
    expected_resource_type: str
    expected_name: str
    expected_sqlbuild_test_type: str
    expected_compiled_code_fragment: str
    expected_depends_on_nodes: tuple[str, ...]


@dataclass(frozen=True)
class ManifestSqlTestNodeTestCase:
    description: str
    project_name: str
    expected_unique_id: str
    expected_resource_type: str
    expected_name: str
    expected_sqlbuild_test_type: str
    expected_compiled_code_fragment: str
    expected_depends_on_nodes: tuple[str, ...]


@dataclass(frozen=True)
class ManifestSchemaValidationTestCase:
    description: str
    project_name: str
    adapter_type: str
    expected_validation_error_count: int


@dataclass(frozen=True)
class FqnTestCase:
    description: str
    project_name: str
    relative_path: str
    expected_fqn: list[str]
