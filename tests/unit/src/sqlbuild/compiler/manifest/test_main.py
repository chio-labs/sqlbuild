from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
    LoadedMacro,
)
from sqlbuild.compiler.manifest.constants import DBT_MANIFEST_SCHEMA_VERSION
from sqlbuild.compiler.manifest.helpers.shared import build_fqn
from sqlbuild.compiler.planner.models import AuditPlanEntry, ChainStep, PlanOutput, SqlTestPlanEntry
from sqlbuild.spec.models.schema import SchemaColumn
from sqlbuild.spec.models.source import SourceColumnEntry
from tests.unit.src.sqlbuild.compiler.manifest._test_types import (
    FqnTestCase,
    ManifestAuditNodeTestCase,
    ManifestMacroNodeTestCase,
    ManifestModelNodeTestCase,
    ManifestParentMapTestCase,
    ManifestSchemaValidationTestCase,
    ManifestSeedNodeTestCase,
    ManifestSourceNodeTestCase,
    ManifestSqlTestNodeTestCase,
    ManifestTopLevelTestCase,
)
from tests.unit.src.sqlbuild.compiler.manifest.helpers import (
    build_test_audit_plan_entry,
    build_test_model,
    build_test_plan_entry,
    build_test_plan_output,
    build_test_project,
    build_test_seed,
    build_test_source,
    build_test_sql_test_plan_entry,
    manifest_macros,
    manifest_nodes,
    manifest_sources,
    model_key,
    run_manifest,
    source_key,
)

_PROJECT: str = "demo"
_ADAPTER: str = "duckdb"

_MODEL_ORDERS: CompiledModel = build_test_model(
    name="orders",
    query_sql="SELECT * FROM raw",
    relative_path="models/staging/orders.sql",
    schema="staging",
    config_values={"materialized": "table"},
    description="Order records",
    columns=(SchemaColumn(name="id", type="INTEGER"),),
)

_MODEL_ORPHAN: CompiledModel = build_test_model(
    name="orphan",
    query_sql="SELECT 1",
    relative_path="models/orphan.sql",
    schema="public",
)

_MODEL_WITH_COLUMNS: CompiledModel = build_test_model(
    name="typed_model",
    relative_path="models/typed_model.sql",
    description="Has columns",
    columns=(
        SchemaColumn(name="id", type="INTEGER", description="Primary key"),
        SchemaColumn(name="status", type="VARCHAR"),
    ),
)

_MODEL_WITH_DEPS: CompiledModel = build_test_model(
    name="joined",
    relative_path="models/joined.sql",
    deps=(model_key("orders"), source_key("raw_customers")),
)

_MODEL_WITH_ALIAS: CompiledModel = build_test_model(
    name="orders_aliased",
    relative_path="models/marts/orders_aliased.sql",
    database="analytics",
    schema="marts",
    alias="fact_orders",
    qualified_name="analytics.marts.fact_orders",
    config_values={"materialized": "incremental", "tags": ["core", "nightly"]},
)

_SOURCE_WITH_COLUMNS: CompiledSource = build_test_source(
    name="raw_events",
    database="raw_db",
    schema="events",
    table="clicks",
    description="Raw click events",
    columns=(
        SourceColumnEntry(name="event_id", type="VARCHAR", description="Event identifier"),
        SourceColumnEntry(name="ts", type="TIMESTAMP"),
    ),
)

_SOURCE_RAW_ORDERS: CompiledSource = build_test_source(
    name="raw_orders",
    database="raw_db",
    schema="public",
    table="orders_table",
    description="Raw order data",
)
_SOURCE_EVENTS: CompiledSource = build_test_source(
    name="events",
    database=None,
    schema="analytics",
)

_SOURCE_FIXTURES: dict[str, Any] = {
    "raw_orders": _SOURCE_RAW_ORDERS,
    "events": _SOURCE_EVENTS,
    "raw_events": _SOURCE_WITH_COLUMNS,
}


MANIFEST_TOP_LEVEL_TEST_CASES: list[ManifestTopLevelTestCase] = [
    ManifestTopLevelTestCase(
        description="produces correct top-level structure for single model project",
        project=build_test_project(
            models=(_MODEL_ORDERS,),
            sources=(build_test_source(name="raw_src"),),
        ),
        plan_output=build_test_plan_output(
            model_entries=(build_test_plan_entry(name="orders"),),
        ),
        loaded_macros={},
        project_name=_PROJECT,
        adapter_type=_ADAPTER,
        upstream_deps={},
        downstream_deps={},
        expected_node_count=1,
        expected_source_count=1,
        expected_macro_count=0,
        expected_metadata_project_name=_PROJECT,
        expected_metadata_adapter_type=_ADAPTER,
        expected_metadata_schema_version=DBT_MANIFEST_SCHEMA_VERSION,
    ),
    ManifestTopLevelTestCase(
        description="produces correct counts for multi-resource project",
        project=build_test_project(
            models=(_MODEL_ORDERS, _MODEL_ORPHAN),
            sources=(build_test_source(name="raw_src"),),
            seeds=(build_test_seed(name="codes"),),
        ),
        plan_output=build_test_plan_output(
            model_entries=(build_test_plan_entry(name="orders"),),
        ),
        loaded_macros={},
        project_name=_PROJECT,
        adapter_type=_ADAPTER,
        upstream_deps={},
        downstream_deps={},
        expected_node_count=3,
        expected_source_count=1,
        expected_macro_count=0,
        expected_metadata_project_name=_PROJECT,
        expected_metadata_adapter_type=_ADAPTER,
        expected_metadata_schema_version=DBT_MANIFEST_SCHEMA_VERSION,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    MANIFEST_TOP_LEVEL_TEST_CASES,
    ids=[case.description for case in MANIFEST_TOP_LEVEL_TEST_CASES],
)
def test_given_project_when_building_manifest_then_produces_correct_structure(
    test_case: ManifestTopLevelTestCase,
) -> None:
    result: dict[str, Any] = run_manifest(
        project=test_case.project,
        plan_output=test_case.plan_output,
        loaded_macros=test_case.loaded_macros,
        project_name=test_case.project_name,
        adapter_type=test_case.adapter_type,
        upstream_deps=test_case.upstream_deps,
        downstream_deps=test_case.downstream_deps,
    )

    assert result["metadata"]["project_name"] == test_case.expected_metadata_project_name
    assert result["metadata"]["adapter_type"] == test_case.expected_metadata_adapter_type
    assert result["metadata"]["dbt_schema_version"] == test_case.expected_metadata_schema_version
    assert len(result["nodes"]) == test_case.expected_node_count
    assert len(result["sources"]) == test_case.expected_source_count
    assert len(result["macros"]) == test_case.expected_macro_count
    assert result["exposures"] == {}
    assert result["metrics"] == {}
    assert result["groups"] == {}
    assert result["disabled"] == {}


MANIFEST_MODEL_NODE_TEST_CASES: list[ManifestModelNodeTestCase] = [
    ManifestModelNodeTestCase(
        description="produces correct model node with plan entry compiled code",
        model=_MODEL_ORDERS,
        plan_entry=build_test_plan_entry(
            name="orders", resolved_sql="SELECT * FROM staging.raw_orders"
        ),
        project_name=_PROJECT,
        expected_unique_id=f"model.{_PROJECT}.orders",
        expected_resource_type="model",
        expected_database=None,
        expected_schema="staging",
        expected_alias="orders",
        expected_fqn=[_PROJECT, "models", "staging", "orders"],
        expected_raw_code="SELECT * FROM raw",
        expected_compiled_code="SELECT * FROM staging.raw_orders",
        expected_relation_name="staging.orders",
        expected_description="Order records",
        expected_materialized="table",
        expected_checksum_name="sha256",
    ),
    ManifestModelNodeTestCase(
        description="uses raw_code as compiled_code when no plan entry exists",
        model=_MODEL_ORPHAN,
        plan_entry=None,
        project_name=_PROJECT,
        expected_unique_id=f"model.{_PROJECT}.orphan",
        expected_resource_type="model",
        expected_database=None,
        expected_schema="public",
        expected_alias="orphan",
        expected_fqn=[_PROJECT, "models", "orphan"],
        expected_raw_code="SELECT 1",
        expected_compiled_code="SELECT 1",
        expected_relation_name="public.orphan",
        expected_description="",
        expected_materialized="view",
        expected_checksum_name="sha256",
    ),
    ManifestModelNodeTestCase(
        description="model columns appear in manifest node",
        model=_MODEL_WITH_COLUMNS,
        plan_entry=None,
        project_name=_PROJECT,
        expected_unique_id=f"model.{_PROJECT}.typed_model",
        expected_resource_type="model",
        expected_database=None,
        expected_schema="public",
        expected_alias="typed_model",
        expected_fqn=[_PROJECT, "models", "typed_model"],
        expected_raw_code="SELECT 1",
        expected_compiled_code="SELECT 1",
        expected_relation_name="public.typed_model",
        expected_description="Has columns",
        expected_materialized="view",
        expected_checksum_name="sha256",
        expected_column_names=("id", "status"),
        expected_column_types={"id": "INTEGER", "status": "VARCHAR"},
    ),
    ManifestModelNodeTestCase(
        description="depends_on includes upstream model and source ids",
        model=_MODEL_WITH_DEPS,
        plan_entry=None,
        project_name=_PROJECT,
        expected_unique_id=f"model.{_PROJECT}.joined",
        expected_resource_type="model",
        expected_database=None,
        expected_schema="public",
        expected_alias="joined",
        expected_fqn=[_PROJECT, "models", "joined"],
        expected_raw_code="SELECT 1",
        expected_compiled_code="SELECT 1",
        expected_relation_name="public.joined",
        expected_description="",
        expected_materialized="view",
        expected_checksum_name="sha256",
        expected_depends_on_nodes=(
            f"model.{_PROJECT}.orders",
            f"source.{_PROJECT}.raw_customers",
        ),
    ),
    ManifestModelNodeTestCase(
        description="model with explicit alias database and tags",
        model=_MODEL_WITH_ALIAS,
        plan_entry=None,
        project_name=_PROJECT,
        expected_unique_id=f"model.{_PROJECT}.orders_aliased",
        expected_resource_type="model",
        expected_database="analytics",
        expected_schema="marts",
        expected_alias="fact_orders",
        expected_fqn=[_PROJECT, "models", "marts", "orders_aliased"],
        expected_raw_code="SELECT 1",
        expected_compiled_code="SELECT 1",
        expected_relation_name="analytics.marts.fact_orders",
        expected_description="",
        expected_materialized="incremental",
        expected_checksum_name="sha256",
        expected_tags=("core", "nightly"),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    MANIFEST_MODEL_NODE_TEST_CASES,
    ids=[case.description for case in MANIFEST_MODEL_NODE_TEST_CASES],
)
def test_given_model_when_building_manifest_then_produces_correct_node(
    test_case: ManifestModelNodeTestCase,
) -> None:
    plan_entries: tuple = (test_case.plan_entry,) if test_case.plan_entry is not None else ()
    project: CompiledProject = build_test_project(models=(test_case.model,))
    plan_output: PlanOutput = build_test_plan_output(model_entries=plan_entries)

    result: dict[str, Any] = run_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros={},
        project_name=test_case.project_name,
        adapter_type=_ADAPTER,
        upstream_deps={},
        downstream_deps={},
    )

    node: dict[str, Any] = manifest_nodes(result)[test_case.expected_unique_id]

    assert node["unique_id"] == test_case.expected_unique_id
    assert node["resource_type"] == test_case.expected_resource_type
    assert node["database"] == test_case.expected_database
    assert node["schema"] == test_case.expected_schema
    assert node["alias"] == test_case.expected_alias
    assert node["fqn"] == test_case.expected_fqn
    assert node["raw_code"] == test_case.expected_raw_code
    assert node["compiled_code"] == test_case.expected_compiled_code
    assert node["relation_name"] == test_case.expected_relation_name
    assert node["description"] == test_case.expected_description
    assert node["config"]["materialized"] == test_case.expected_materialized
    assert node["checksum"]["name"] == test_case.expected_checksum_name
    assert len(node["checksum"]["checksum"]) == 64
    column_name: str
    for column_name in test_case.expected_column_names:
        assert column_name in node["columns"]
    expected_col: str
    expected_type: str | None
    for expected_col, expected_type in test_case.expected_column_types.items():
        assert node["columns"][expected_col]["data_type"] == expected_type
    dep_id: str
    for dep_id in test_case.expected_depends_on_nodes:
        assert dep_id in node["depends_on"]["nodes"]
    tag: str
    for tag in test_case.expected_tags:
        assert tag in node["tags"]


MANIFEST_SOURCE_NODE_TEST_CASES: list[ManifestSourceNodeTestCase] = [
    ManifestSourceNodeTestCase(
        description="produces correct source node fields",
        project_name=_PROJECT,
        expected_unique_id=f"source.{_PROJECT}.raw_orders",
        expected_resource_type="source",
        expected_database="raw_db",
        expected_schema="public",
        expected_identifier="orders_table",
        expected_description="Raw order data",
        expected_source_name="raw_orders",
    ),
    ManifestSourceNodeTestCase(
        description="uses source name as identifier when table is absent",
        project_name=_PROJECT,
        expected_unique_id=f"source.{_PROJECT}.events",
        expected_resource_type="source",
        expected_database=None,
        expected_schema="analytics",
        expected_identifier="events",
        expected_description="",
        expected_source_name="events",
    ),
    ManifestSourceNodeTestCase(
        description="source columns appear in manifest source node",
        project_name=_PROJECT,
        expected_unique_id=f"source.{_PROJECT}.raw_events",
        expected_resource_type="source",
        expected_database="raw_db",
        expected_schema="events",
        expected_identifier="clicks",
        expected_description="Raw click events",
        expected_source_name="raw_events",
        expected_column_names=("event_id", "ts"),
        expected_column_types={"event_id": "VARCHAR", "ts": "TIMESTAMP"},
    ),
]


@pytest.mark.parametrize(
    "test_case",
    MANIFEST_SOURCE_NODE_TEST_CASES,
    ids=[case.description for case in MANIFEST_SOURCE_NODE_TEST_CASES],
)
def test_given_source_when_building_manifest_then_produces_correct_node(
    test_case: ManifestSourceNodeTestCase,
) -> None:
    source: CompiledSource = _SOURCE_FIXTURES[test_case.expected_source_name]
    project: CompiledProject = build_test_project(sources=(source,))
    plan_output: PlanOutput = build_test_plan_output()

    result: dict[str, Any] = run_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros={},
        project_name=test_case.project_name,
        adapter_type=_ADAPTER,
        upstream_deps={},
        downstream_deps={},
    )

    node: dict[str, Any] = manifest_sources(result)[test_case.expected_unique_id]

    assert node["unique_id"] == test_case.expected_unique_id
    assert node["resource_type"] == test_case.expected_resource_type
    assert node["database"] == test_case.expected_database
    assert node["schema"] == test_case.expected_schema
    assert node["identifier"] == test_case.expected_identifier
    assert node["description"] == test_case.expected_description
    col_name: str
    for col_name in test_case.expected_column_names:
        assert col_name in node["columns"]
    expected_col: str
    expected_type: str | None
    for expected_col, expected_type in test_case.expected_column_types.items():
        assert node["columns"][expected_col]["data_type"] == expected_type


@pytest.mark.parametrize(
    "test_case",
    [
        ManifestSeedNodeTestCase(
            description="produces correct seed node with materialized seed",
            project_name=_PROJECT,
            expected_unique_id=f"seed.{_PROJECT}.country_codes",
            expected_resource_type="seed",
            expected_materialized="seed",
        ),
    ],
    ids=["produces correct seed node with materialized seed"],
)
def test_given_seed_when_building_manifest_then_produces_correct_node(
    test_case: ManifestSeedNodeTestCase,
) -> None:
    seed: CompiledSeed = build_test_seed(name="country_codes")
    project: CompiledProject = build_test_project(seeds=(seed,))
    plan_output: PlanOutput = build_test_plan_output()

    result: dict[str, Any] = run_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros={},
        project_name=test_case.project_name,
        adapter_type=_ADAPTER,
        upstream_deps={},
        downstream_deps={},
    )

    node: dict[str, Any] = manifest_nodes(result)[test_case.expected_unique_id]

    assert node["unique_id"] == test_case.expected_unique_id
    assert node["resource_type"] == test_case.expected_resource_type
    assert node["config"]["materialized"] == test_case.expected_materialized


FQN_TEST_CASES: list[FqnTestCase] = [
    FqnTestCase(
        description="builds fqn from nested relative path",
        project_name=_PROJECT,
        relative_path="models/staging/orders.sql",
        expected_fqn=[_PROJECT, "models", "staging", "orders"],
    ),
    FqnTestCase(
        description="builds fqn from top-level relative path",
        project_name=_PROJECT,
        relative_path="models/orders.sql",
        expected_fqn=[_PROJECT, "models", "orders"],
    ),
    FqnTestCase(
        description="builds fqn from seed path",
        project_name=_PROJECT,
        relative_path="seeds/codes.csv",
        expected_fqn=[_PROJECT, "seeds", "codes"],
    ),
]


@pytest.mark.parametrize(
    "test_case",
    FQN_TEST_CASES,
    ids=[case.description for case in FQN_TEST_CASES],
)
def test_given_relative_path_when_building_fqn_then_returns_expected_parts(
    test_case: FqnTestCase,
) -> None:
    result: list[str] = build_fqn(
        project_name=test_case.project_name,
        relative_path=Path(test_case.relative_path),
    )

    assert result == test_case.expected_fqn


@pytest.mark.parametrize(
    "test_case",
    [
        ManifestParentMapTestCase(
            description="parent_map reflects upstream dependencies",
            project_name=_PROJECT,
            expected_parent_entry=(
                f"model.{_PROJECT}.orders",
                [f"source.{_PROJECT}.raw_orders"],
            ),
            expected_child_entry=(
                f"source.{_PROJECT}.raw_orders",
                [f"model.{_PROJECT}.orders"],
            ),
        ),
    ],
    ids=["parent_map reflects upstream dependencies"],
)
def test_given_deps_when_building_manifest_then_parent_map_correct(
    test_case: ManifestParentMapTestCase,
) -> None:
    source: CompiledSource = build_test_source(name="raw_orders")
    model: CompiledModel = build_test_model(name="orders", deps=(source_key("raw_orders"),))
    project: CompiledProject = build_test_project(models=(model,), sources=(source,))
    plan_output: PlanOutput = build_test_plan_output(
        model_entries=(build_test_plan_entry(name="orders"),),
    )

    orders_k: CompiledObjectKey = model_key("orders")
    raw_k: CompiledObjectKey = source_key("raw_orders")
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        orders_k: (raw_k,),
        raw_k: (),
    }
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        raw_k: (orders_k,),
        orders_k: (),
    }

    result: dict[str, Any] = run_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros={},
        project_name=test_case.project_name,
        adapter_type=_ADAPTER,
        upstream_deps=upstream,
        downstream_deps=downstream,
    )

    parent_key: str = test_case.expected_parent_entry[0]
    parent_values: list[str] = test_case.expected_parent_entry[1]
    assert result["parent_map"][parent_key] == parent_values

    child_key: str = test_case.expected_child_entry[0]
    child_values: list[str] = test_case.expected_child_entry[1]
    assert result["child_map"][child_key] == child_values


@pytest.mark.parametrize(
    "test_case",
    [
        ManifestMacroNodeTestCase(
            description="macro appears in manifest macros dict",
            project_name=_PROJECT,
            expected_unique_id=f"macro.{_PROJECT}.my_macro",
            expected_name="my_macro",
            expected_resource_type="macro",
            expected_macro_sql="def my_macro(): return 'SELECT 1'",
            expected_path="macros/helpers.py",
        ),
    ],
    ids=["macro appears in manifest macros dict"],
)
def test_given_macro_when_building_manifest_then_macro_node_present(
    test_case: ManifestMacroNodeTestCase,
) -> None:
    macro: LoadedMacro = LoadedMacro(
        name=test_case.expected_name,
        file_path=Path(f"/project/{test_case.expected_path}"),
        relative_path=Path(test_case.expected_path),
        raw_source=test_case.expected_macro_sql,
        function=lambda: "SELECT 1",
    )
    project: CompiledProject = build_test_project()
    plan_output: PlanOutput = build_test_plan_output()

    result: dict[str, Any] = run_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros={test_case.expected_name: macro},
        project_name=test_case.project_name,
        adapter_type=_ADAPTER,
        upstream_deps={},
        downstream_deps={},
    )

    macro_node: dict[str, Any] = manifest_macros(result)[test_case.expected_unique_id]

    assert macro_node["name"] == test_case.expected_name
    assert macro_node["resource_type"] == test_case.expected_resource_type
    assert macro_node["macro_sql"] == test_case.expected_macro_sql
    assert macro_node["path"] == test_case.expected_path


@pytest.mark.parametrize(
    "test_case",
    [
        ManifestAuditNodeTestCase(
            description="audit plan entry produces dbt test node with test_metadata",
            project_name=_PROJECT,
            expected_unique_id=f"test.{_PROJECT}.not_null_orders_id",
            expected_resource_type="test",
            expected_name="not_null_orders_id",
            expected_sqlbuild_test_type="audit",
            expected_compiled_code_fragment="WHERE id IS NULL",
            expected_depends_on_nodes=(f"model.{_PROJECT}.orders",),
        ),
    ],
    ids=["audit plan entry produces dbt test node with test_metadata"],
)
def test_given_audit_when_building_manifest_then_produces_test_node(
    test_case: ManifestAuditNodeTestCase,
) -> None:
    model: CompiledModel = build_test_model(name="orders")
    project: CompiledProject = build_test_project(models=(model,))
    audit_entry: AuditPlanEntry = build_test_audit_plan_entry(
        name="not_null_orders_id",
        resolved_sql="SELECT id FROM staging.orders WHERE id IS NULL",
        scope_deps=(model_key("orders"),),
        attached_target_name="orders",
        attached_column_name="id",
    )
    plan_output: PlanOutput = build_test_plan_output(
        model_entries=(build_test_plan_entry(name="orders"),),
        audit_entries=(audit_entry,),
    )

    result: dict[str, Any] = run_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros={},
        project_name=test_case.project_name,
        adapter_type=_ADAPTER,
        upstream_deps={},
        downstream_deps={},
    )

    node: dict[str, Any] = manifest_nodes(result)[test_case.expected_unique_id]

    assert node["unique_id"] == test_case.expected_unique_id
    assert node["resource_type"] == test_case.expected_resource_type
    assert node["name"] == test_case.expected_name
    assert node["meta"]["sqlbuild_test_type"] == test_case.expected_sqlbuild_test_type
    assert test_case.expected_compiled_code_fragment in node["compiled_code"]
    dep_id: str
    for dep_id in test_case.expected_depends_on_nodes:
        assert dep_id in node["depends_on"]["nodes"]


@pytest.mark.parametrize(
    "test_case",
    [
        ManifestSqlTestNodeTestCase(
            description="sql test plan entry produces dbt test node with chain steps",
            project_name=_PROJECT,
            expected_unique_id=f"test.{_PROJECT}.test_orders",
            expected_resource_type="test",
            expected_name="test_orders",
            expected_sqlbuild_test_type="sql_native",
            expected_compiled_code_fragment="-- step: orders",
            expected_depends_on_nodes=(f"model.{_PROJECT}.orders",),
        ),
    ],
    ids=["sql test plan entry produces dbt test node with chain steps"],
)
def test_given_sql_test_when_building_manifest_then_produces_test_node(
    test_case: ManifestSqlTestNodeTestCase,
) -> None:
    model: CompiledModel = build_test_model(name="orders")
    project: CompiledProject = build_test_project(models=(model,))
    chain: tuple[ChainStep, ...] = (
        ChainStep(
            model_name="orders",
            resolved_sql="SELECT 1 AS id",
            expected_cte_sql="SELECT 1 AS id",
        ),
    )
    test_entry: SqlTestPlanEntry = build_test_sql_test_plan_entry(
        name="test_orders",
        chain=chain,
        scope_deps=(model_key("orders"),),
    )
    plan_output: PlanOutput = build_test_plan_output(
        model_entries=(build_test_plan_entry(name="orders"),),
        test_entries=(test_entry,),
    )

    result: dict[str, Any] = run_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros={},
        project_name=test_case.project_name,
        adapter_type=_ADAPTER,
        upstream_deps={},
        downstream_deps={},
    )

    node: dict[str, Any] = manifest_nodes(result)[test_case.expected_unique_id]

    assert node["unique_id"] == test_case.expected_unique_id
    assert node["resource_type"] == test_case.expected_resource_type
    assert node["name"] == test_case.expected_name
    assert node["meta"]["sqlbuild_test_type"] == test_case.expected_sqlbuild_test_type
    assert test_case.expected_compiled_code_fragment in node["compiled_code"]
    dep_id: str
    for dep_id in test_case.expected_depends_on_nodes:
        assert dep_id in node["depends_on"]["nodes"]


@pytest.mark.parametrize(
    "test_case",
    [
        ManifestSchemaValidationTestCase(
            description="full manifest validates against dbt v12 json schema",
            project_name=_PROJECT,
            adapter_type=_ADAPTER,
            expected_validation_error_count=0,
        ),
    ],
    ids=["full manifest validates against dbt v12 json schema"],
)
def test_given_full_project_when_building_manifest_then_validates_against_dbt_schema(
    test_case: ManifestSchemaValidationTestCase,
) -> None:
    import json

    from jsonschema import Draft202012Validator

    schema_path: Path = (
        Path(__file__).resolve().parents[5] / "fixtures" / "dbt_manifest_v12_schema.json"
    )
    schema: dict[str, Any] = json.loads(schema_path.read_text(encoding="utf-8"))

    model: CompiledModel = build_test_model(
        name="orders",
        query_sql="SELECT id FROM raw",
        relative_path="models/staging/orders.sql",
        schema="staging",
        config_values={"materialized": "table", "tags": ["core"]},
        description="Order records",
        columns=(SchemaColumn(name="id", type="INTEGER"),),
        deps=(source_key("raw_orders"),),
    )
    source: CompiledSource = build_test_source(
        name="raw_orders",
        database="raw_db",
        schema="public",
        table="orders",
    )
    seed: CompiledSeed = build_test_seed(name="codes")
    project: CompiledProject = build_test_project(
        models=(model,),
        sources=(source,),
        seeds=(seed,),
    )
    plan_output: PlanOutput = build_test_plan_output(
        model_entries=(
            build_test_plan_entry(
                name="orders", resolved_sql="SELECT id FROM raw_db.public.orders"
            ),
        ),
        audit_entries=(
            build_test_audit_plan_entry(
                name="not_null_orders_id",
                scope_deps=(model_key("orders"),),
            ),
        ),
        test_entries=(
            build_test_sql_test_plan_entry(
                name="test_orders",
                chain=(
                    ChainStep(
                        model_name="orders", resolved_sql="SELECT 1", expected_cte_sql="SELECT 1"
                    ),
                ),
                scope_deps=(model_key("orders"),),
            ),
        ),
    )

    orders_key: CompiledObjectKey = model_key("orders")
    raw_key: CompiledObjectKey = source_key("raw_orders")
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        orders_key: (raw_key,),
        raw_key: (),
    }
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        raw_key: (orders_key,),
        orders_key: (),
    }

    macro: LoadedMacro = LoadedMacro(
        name="my_macro",
        file_path=Path("/project/macros/helpers.py"),
        relative_path=Path("macros/helpers.py"),
        raw_source="def my_macro(): return 'SELECT 1'",
        function=lambda: "SELECT 1",
    )

    result: dict[str, Any] = run_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros={"my_macro": macro},
        project_name=test_case.project_name,
        adapter_type=test_case.adapter_type,
        upstream_deps=upstream,
        downstream_deps=downstream,
    )

    validator: Any = Draft202012Validator(schema)
    errors: list[Any] = list(validator.iter_errors(result))
    error_messages: list[str] = [f"{list(e.absolute_path)}: {e.message}" for e in errors]

    assert len(errors) == test_case.expected_validation_error_count, (
        "Schema validation errors:\n" + "\n".join(error_messages)
    )
