from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledProject, CompileModelConfig
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_MODEL
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.graph.scope import build_planner_scope
from sqlbuild.compiler.planner.helpers.identity.standard import (
    build_standard_model_version_identities,
)
from sqlbuild.compiler.planner.models import StandardModelVersionIdentities
from sqlbuild.shared.helpers.hashing import compute_query_hash
from tests.unit.src.sqlbuild.integrations.dbt.helpers import build_compiled_project_with_models


def build_standard_pruning_project(
    sql_by_model_name: dict[str, str],
    *,
    model_configs: dict[str, dict[str, object]] | None = None,
) -> CompiledProject:
    project: CompiledProject = build_compiled_project_with_models(sql_by_model_name)
    configs: dict[str, dict[str, object]] = model_configs or {}
    models: list[CompiledModel] = []
    model: CompiledModel
    for model in project.models:
        models.append(
            replace(
                model,
                config=CompileModelConfig(values=configs.get(model.name, model.config.values)),
                destination=replace(
                    model.destination,
                    schema="staging",
                    qualified_name=f"staging.{model.name}",
                ),
            )
        )
    return replace(project, effective_target_schema="staging", models=tuple(models))


def build_standard_project_for_schema(
    sql_by_model_name: dict[str, str], *, schema: str, effective_target_name: str = "dev"
) -> CompiledProject:
    project: CompiledProject = build_compiled_project_with_models(sql_by_model_name)
    models: list[CompiledModel] = []
    model: CompiledModel
    for model in project.models:
        models.append(
            replace(
                model,
                destination=replace(
                    model.destination,
                    schema=schema,
                    qualified_name=f"{schema}.{model.name}",
                ),
            )
        )
    return replace(
        project,
        effective_target_name=effective_target_name,
        effective_target_schema=schema,
        models=tuple(models),
    )


def write_standard_model_state(
    *, adapter: DuckDbAdapter, connection: object, project: CompiledProject
) -> StandardModelVersionIdentities:
    adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS staging")
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
        adapter.execute(
            connection,
            f"CREATE OR REPLACE TABLE staging.{model.name} AS SELECT 1 AS id",
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


def write_standard_model_state_for_schema(
    *,
    adapter: DuckDbAdapter,
    connection: object,
    project: CompiledProject,
    schema: str,
    create_relations: bool = True,
) -> StandardModelVersionIdentities:
    adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema}")
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
        if create_relations:
            adapter.execute(
                connection,
                f"CREATE OR REPLACE TABLE {schema}.{model.name} AS SELECT 1 AS id",
            )
        write_fingerprint(
            connection=connection,
            execute=adapter.execute,
            database=None,
            schema=schema,
            fingerprint=Fingerprint(
                node_type=NODE_TYPE_MODEL,
                node_name=model.name,
                target_database=None,
                target_schema=schema,
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
