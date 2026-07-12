from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_MODEL
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.graph.scope import build_planner_scope
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


def write_standard_model_state(
    *, adapter: DuckDbAdapter, connection: object, project: CompiledProject
) -> StandardModelVersionIdentities:
    adapter.execute(connection=connection, sql="CREATE SCHEMA IF NOT EXISTS staging")
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
            connection=connection,
            sql=f"CREATE OR REPLACE TABLE staging.{model.name} AS SELECT 1 AS id",
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


def model_definition_hash(project: CompiledProject, name: str) -> str:
    model: CompiledModel = next(model for model in project.models if model.name == name)
    return compute_query_hash(model.query_sql)


def build_sqlbuild_model_selector_project() -> CompiledProject:
    return CompiledProject(
        run_id="selector-test-run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=(
            build_sqlbuild_model_selector_model(
                name="fact_orders",
                relative_path=Path("models/marts/fact_orders.sql"),
                tags=("nightly",),
            ),
            build_sqlbuild_model_selector_model(
                name="dim_customers",
                relative_path=Path("models/marts/dim_customers.sql"),
                tags=("nightly", "customer"),
            ),
            build_sqlbuild_model_selector_model(
                name="stg_orders",
                relative_path=Path("models/staging/stg_orders.sql"),
                tags=("staging",),
            ),
        ),
    )


def build_sqlbuild_model_selector_model(
    *, name: str, relative_path: Path, tags: tuple[str, ...]
) -> CompiledModel:
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        deps=(),
        name=name,
        relative_path=relative_path,
        query_sql=f"SELECT 1 AS {name}",
        config=CompileModelConfig(values={"tags": tags}),
        destination=CompiledRelationLocation(
            database=None,
            schema=None,
            name=name,
            qualified_name=None,
        ),
    )


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
