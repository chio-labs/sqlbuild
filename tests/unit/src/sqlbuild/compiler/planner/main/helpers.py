from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.planner.main.execution.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlannerOverrides,
    PlannerPolicies,
    PlannerSelection,
    PlanOutput,
)
from sqlbuild.spec.contracts.models import SchemaColumn, SchemaModelEntry


def model_definition_hash(project: CompiledProject, name: str) -> str:
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in project.models}
    model: CompiledModel = models_by_name[name]
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
        return {name: kwargs.pop(name) for name in names & kwargs.keys()}

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


def build_protected_schema_replay_project() -> CompiledProject:
    """Build a full_refresh false incremental whose declared column forces a full replay."""

    model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="order_history"),
        deps=(),
        name="order_history",
        relative_path=Path("models/order_history.sql"),
        query_sql="SELECT 1 AS id, 2 AS amount",
        config=CompileModelConfig(
            values={
                "materialized": "incremental",
                "incremental_strategy": "append",
                "replay_on_change": "full",
                "full_refresh": False,
            }
        ),
        destination=CompiledRelationLocation(
            database=None, schema="main", name="order_history", qualified_name="main.order_history"
        ),
        schema_entry=SchemaModelEntry(
            name="order_history",
            columns=(
                SchemaColumn(name="id", type="INTEGER"),
                SchemaColumn(name="amount", type="INTEGER"),
            ),
        ),
    )
    return CompiledProject(
        run_id="protected-rebuild-run",
        effective_target_name=None,
        effective_connection={},
        effective_vars={},
        models=(model,),
    )
