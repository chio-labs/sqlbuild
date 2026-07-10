"""Test helpers for planner orchestration integration tests."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile.helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
    CompileModelInput,
    CompileProjectInputs,
    CompileSqlReference,
    FunctionArgument,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
)
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_MODEL
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.graph.scope import build_planner_scope
from sqlbuild.compiler.planner.helpers.identity.functions import (
    build_compiled_function_fingerprint_sql,
)
from sqlbuild.compiler.planner.helpers.identity.standard import (
    build_standard_model_version_identities,
)
from sqlbuild.compiler.planner.main.planning.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlannerOverrides,
    PlannerPolicies,
    PlannerSelection,
    PlanOutput,
    StandardModelVersionIdentities,
)
from sqlbuild.shared.helpers.identity.hashing import compute_query_hash
from sqlbuild.shared.types import SqlReferenceKind
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, SettingsConfig
from sqlbuild.spec.models.schema import SchemaSeedEntry
from sqlbuild.spec.models.source import SourceEntry
from tests.integration.src.sqlbuild.compiler.planner.main._test_types import (
    BuildExecutionPlanTestCase,
    FormatPlanIntegrationTestCase,
    SourceCursorInputPlanErrorTestCase,
)


def build_project_from_test_case(
    test_case: BuildExecutionPlanTestCase,
) -> CompiledProject:
    """Build a CompiledProject from an integration test case."""

    models: list[CompiledModel] = []
    model_name: str
    target_schema: str
    for model_name, target_schema in test_case.model_locations.items():
        config_values: dict[str, object] = test_case.model_configs.get(model_name, {})
        query_sql: str = test_case.model_queries.get(model_name, f"SELECT * FROM {model_name}")
        dep_names: tuple[str, ...] = test_case.model_deps.get(model_name, ())
        model_deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=d) for d in dep_names
        )
        function_deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.UDF, name=d)
            for d in test_case.function_deps.get(model_name, ())
        )
        models.append(
            CompiledModel(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL,
                    name=model_name,
                ),
                deps=(*model_deps, *function_deps),
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql=query_sql,
                config=CompileModelConfig(values=config_values),
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=model_name,
                    qualified_name=f"{target_schema}.{model_name}",
                ),
            )
        )

    seeds: list[CompiledSeed] = []
    seed_name: str
    for seed_name, target_schema in test_case.seed_locations.items():
        seed_file_path: Path = _ensure_test_seed_file(seed_name)
        seeds.append(
            CompiledSeed(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SEED,
                    name=seed_name,
                ),
                deps=(),
                name=seed_name,
                seed_file=DiscoveredSeedFile(
                    file_path=seed_file_path,
                    relative_path=Path(f"seeds/{seed_name}.csv"),
                ),
                schema_entry=SchemaSeedEntry(name=seed_name, columns=()),
                schema_file=DiscoveredSchemaFile(
                    file_path=Path("seeds/schema.yml"),
                    relative_path=Path("seeds/schema.yml"),
                    contents="",
                    model_entries=(),
                    seed_entries=(),
                ),
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=seed_name,
                    qualified_name=f"{target_schema}.{seed_name}",
                ),
            )
        )

    functions: list[CompiledFunction] = []
    function_name: str
    for function_name, target_schema in test_case.function_locations.items():
        body_sql: str = test_case.function_bodies.get(function_name, "value = 1")
        language: FunctionLanguage = test_case.function_languages.get(
            function_name, FunctionLanguage.SQL
        )
        functions.append(
            CompiledFunction(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.UDF,
                    name=function_name,
                ),
                deps=(),
                name=function_name,
                relative_path=Path(f"functions/{language.value}/{function_name}.sql"),
                arguments=(FunctionArgument(name="value", type="INTEGER"),),
                returns="INTEGER",
                body_sql=body_sql,
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=function_name,
                    qualified_name=f"{target_schema}.{function_name}",
                ),
                fingerprint_destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=function_name,
                    qualified_name=f"{target_schema}.{function_name}",
                ),
                language=language,
                entry_point="main" if language == FunctionLanguage.PYTHON else None,
                replay_on_change=test_case.function_replay_on_changes.get(function_name),
            )
        )

    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection=test_case.effective_connection,
        effective_vars={},
        settings=SettingsConfig(
            sql_analysis=_settings_bool(
                test_case.effective_connection, "sql_analysis", default=False
            )
        ),
        models=tuple(models),
        seeds=tuple(seeds),
        functions=tuple(functions),
    )


def build_standard_pruning_project(
    sql_by_model_name: dict[str, str],
    model_configs: dict[str, dict[str, object]] | None = None,
) -> CompiledProject:
    """Build a compiled standard project with real refs and a staging target schema."""

    model_inputs: list[CompileModelInput] = []
    model_name: str
    sql: str
    for model_name, sql in sql_by_model_name.items():
        relative_path: Path = Path(f"models/{model_name}.sql")
        model_file: DiscoveredSqlModelFile = DiscoveredSqlModelFile(
            file_path=Path("/repo") / relative_path,
            relative_path=relative_path,
            contents=f"MODEL ();\n\n{sql}\n",
            header_values={},
            header_column_locations={},
            output_column_locations={},
            query_sql=sql,
        )
        config_values: dict[str, object] = (model_configs or {}).get(model_name, {})
        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                config=CompileModelConfig(values=config_values),
                query_sql=sql,
                references=extract_sql_references(sql),
            )
        )
    project: CompiledProject = assemble_compiled_project(
        CompileProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            discovered_inputs=DiscoveredProjectInputs(
                project_config=ProjectConfig(name="demo", adapter="duckdb"),
                local_config=LocalConfig(),
            ),
            model_inputs=tuple(model_inputs),
        )
    )
    models: list[CompiledModel] = []
    model: CompiledModel
    for model in project.models:
        models.append(
            replace(
                model,
                destination=replace(
                    model.destination,
                    schema="staging",
                    qualified_name=f"staging.{model.name}",
                ),
            )
        )
    return replace(project, effective_target_schema="staging", models=tuple(models))


def write_standard_model_state(
    *, adapter: DuckDbAdapter, connection: Any, project: CompiledProject
) -> StandardModelVersionIdentities:
    """Create prior model relations and matching standard fingerprints."""

    adapter.execute(connection, sql="CREATE SCHEMA IF NOT EXISTS staging")
    identities: StandardModelVersionIdentities = build_standard_model_version_identities(
        functions=project.functions,
        seeds=project.seeds,
        scope=build_planner_scope(
            project=project,
            select=(),
            exclude=(),
            auto_load_sources=False,
        ),
    )
    model: CompiledModel
    for model in project.models:
        config_values: dict[str, object] = model.config.values
        materialized: object | None = config_values.get("materialized")
        existing_relation_sql: str = "VIEW" if materialized == "view" else "TABLE"
        adapter.execute(
            connection,
            sql=f"CREATE OR REPLACE {existing_relation_sql} staging.{model.name} AS SELECT 1 AS id",
        )
        write_fingerprint(
            connection=connection,
            execute=adapter.execute,
            database=None,
            schema="staging",
            fingerprint=Fingerprint(
                node_type=NODE_TYPE_MODEL,
                node_name=model.name,
                target_database=None,
                target_schema="staging",
                target_name=model.name,
                run_id="previous_run",
                definition_hash=compute_query_hash(model.query_sql),
                version_hash=identities.model_version_hashes[model.name],
                schema_fingerprint=compute_query_hash(""),
                definition=model.query_sql,
                metadata_json=identities.model_metadata_jsons[model.name],
                ts=datetime.now(UTC),
            ),
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )
    return identities


def _settings_bool(settings: dict[str, object], key: str, *, default: bool) -> bool:
    """Read a boolean setting from legacy test-case settings dictionaries."""

    raw_value: object | None = settings.get(key)
    if isinstance(raw_value, bool):
        return raw_value
    return default


def build_project_from_source_cursor_input_test_case(
    test_case: SourceCursorInputPlanErrorTestCase,
) -> CompiledProject:
    """Build a project with one incremental model reading one source."""

    source_entry: SourceEntry = SourceEntry(
        name=test_case.source_name,
        schema=test_case.source_schema,
        table=test_case.source_table,
    )
    source: CompiledSource = CompiledSource(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SOURCE,
            name=test_case.source_name,
        ),
        deps=(),
        name=test_case.source_name,
        source_entry=source_entry,
        source_file=DiscoveredSourceFile(
            file_path=Path("sources/raw.yml"),
            relative_path=Path("sources/raw.yml"),
            contents="",
            source_entries=(source_entry,),
        ),
    )
    model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL,
            name=test_case.model_name,
        ),
        deps=(source.key,),
        name=test_case.model_name,
        relative_path=Path(f"models/{test_case.model_name}.sql"),
        query_sql=f'SELECT * FROM __source("{test_case.source_name}")',
        references=(
            CompileSqlReference(
                ref_kind=SqlReferenceKind.SOURCE,
                ref_name=test_case.source_name,
            ),
        ),
        config=CompileModelConfig(
            values={
                "materialized": "incremental",
                "cursor": test_case.cursor_column,
                "cursor_inputs": {test_case.source_name: test_case.cursor_input_column},
            }
        ),
        destination=CompiledRelationLocation(
            database=None,
            schema="staging",
            name=test_case.model_name,
            qualified_name=f"staging.{test_case.model_name}",
        ),
    )
    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        settings=SettingsConfig(),
        models=(model,),
        sources=(source,),
    )


def write_previous_function_fingerprints(
    *,
    test_case: BuildExecutionPlanTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    """Write previous function definition fingerprints for planner tests."""

    if not test_case.previous_function_bodies:
        return
    previous_case: BuildExecutionPlanTestCase = replace(
        test_case,
        function_bodies={**test_case.function_bodies, **test_case.previous_function_bodies},
    )
    previous_project: CompiledProject = build_project_from_test_case(previous_case)
    function_map: dict[str, CompiledFunction] = {
        function.name: function for function in previous_project.functions
    }
    function_name: str
    for function_name in test_case.previous_function_bodies:
        function: CompiledFunction = function_map[function_name]
        fingerprint_sql: str = build_compiled_function_fingerprint_sql(function)
        write_fingerprint(
            connection=connection,
            execute=adapter.execute,
            database=function.destination.database,
            schema=function.destination.schema or "",
            fingerprint=Fingerprint(
                node_type="table_fn" if function.return_columns else "udf",
                node_name=function.name,
                target_database=function.destination.database,
                target_schema=function.destination.schema,
                target_name=function.destination.name,
                run_id="previous_run",
                definition_hash=compute_query_hash(fingerprint_sql),
                schema_fingerprint=compute_query_hash(""),
                definition=fingerprint_sql,
                ts=datetime.now(tz=UTC),
            ),
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )


def build_project_from_format_test_case(
    test_case: FormatPlanIntegrationTestCase,
) -> CompiledProject:
    """Build a CompiledProject from a format integration test case."""

    models: list[CompiledModel] = []
    model_name: str
    target_schema: str
    for model_name, target_schema in test_case.model_locations.items():
        config_values: dict[str, object] = test_case.model_configs.get(model_name, {})
        query_sql: str = test_case.model_queries.get(model_name, f"SELECT * FROM {model_name}")
        dep_names: tuple[str, ...] = test_case.model_deps.get(model_name, ())
        deps: tuple[CompiledObjectKey, ...] = tuple(
            CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=d) for d in dep_names
        )
        models.append(
            CompiledModel(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.MODEL,
                    name=model_name,
                ),
                deps=deps,
                name=model_name,
                relative_path=Path(f"models/{model_name}.sql"),
                query_sql=query_sql,
                config=CompileModelConfig(values=config_values),
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=model_name,
                    qualified_name=f"{target_schema}.{model_name}",
                ),
            )
        )

    seeds: list[CompiledSeed] = []
    seed_name: str
    for seed_name, target_schema in test_case.seed_locations.items():
        seed_file_path: Path = _ensure_test_seed_file(seed_name)
        seeds.append(
            CompiledSeed(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SEED,
                    name=seed_name,
                ),
                deps=(),
                name=seed_name,
                seed_file=DiscoveredSeedFile(
                    file_path=seed_file_path,
                    relative_path=Path(f"seeds/{seed_name}.csv"),
                ),
                schema_entry=SchemaSeedEntry(name=seed_name, columns=()),
                schema_file=DiscoveredSchemaFile(
                    file_path=Path("seeds/schema.yml"),
                    relative_path=Path("seeds/schema.yml"),
                    contents="",
                    model_entries=(),
                    seed_entries=(),
                ),
                destination=CompiledRelationLocation(
                    database=None,
                    schema=target_schema,
                    name=seed_name,
                    qualified_name=f"{target_schema}.{seed_name}",
                ),
            )
        )

    return CompiledProject(
        run_id="test_run",
        effective_target_name=None,
        effective_connection=test_case.effective_connection,
        effective_vars={},
        models=tuple(models),
        seeds=tuple(seeds),
    )


def _ensure_test_seed_file(seed_name: str) -> Path:
    seed_dir: Path = Path(gettempdir()) / "sqlbuild_planner_seed_fixtures"
    seed_dir.mkdir(parents=True, exist_ok=True)
    seed_path: Path = seed_dir / f"{seed_name}.csv"
    if not seed_path.exists():
        seed_path.write_text("id,code\n1,US\n", encoding="utf-8")
    return seed_path


def build_execution_plan_from_kwargs(**kwargs: Any) -> PlanOutput:
    """Adapt flat planner kwargs to the grouped build_execution_plan inputs."""

    def grouped(model: type) -> dict[str, Any]:
        names: frozenset[str] = frozenset(field.name for field in fields(model))
        return {name: kwargs.pop(name) for name in list(kwargs) if name in names}

    selection: PlannerSelection = PlannerSelection(**grouped(PlannerSelection))
    overrides: PlannerOverrides = PlannerOverrides(**grouped(PlannerOverrides))
    deferral: DeferralInputs = DeferralInputs(**grouped(DeferralInputs))
    policies: PlannerPolicies = PlannerPolicies(**grouped(PlannerPolicies))
    return build_execution_plan(
        selection=selection,
        overrides=overrides,
        deferral=deferral,
        policies=policies,
        **kwargs,
    )
