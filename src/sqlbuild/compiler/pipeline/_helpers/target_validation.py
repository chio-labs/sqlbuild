"""Adapter-aware target namespace validation."""

from __future__ import annotations

from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError


def validate_project_targets(*, adapter_name: str, project: CompiledProject) -> None:
    """Validate compiled model and seed locations for the effective adapter."""

    if adapter_name not in {
        BuiltinAdapter.SNOWFLAKE,
        BuiltinAdapter.BIGQUERY,
        BuiltinAdapter.DATABRICKS,
    }:
        return
    _validate_required_target_parts(
        adapter_name=adapter_name,
        resource_kind="model",
        targets={model.name: model.destination for model in project.models},
    )
    _validate_required_target_parts(
        adapter_name=adapter_name,
        resource_kind="seed",
        targets={seed.name: seed.destination for seed in project.seeds},
    )


def _validate_required_target_parts(
    *,
    adapter_name: str,
    resource_kind: str,
    targets: dict[str, CompiledRelationLocation],
) -> None:
    resource_name: str
    target: CompiledRelationLocation
    for resource_name, target in targets.items():
        missing_parts: list[str] = []
        if target.database is None:
            missing_parts.append("database")
        if target.schema is None:
            missing_parts.append("schema")
        if not missing_parts:
            continue
        missing_text: str = ", ".join(missing_parts)
        raise PlannerInputError(
            f"{adapter_name} execution requires explicit target {missing_text}. "
            f"{resource_kind} '{resource_name}' resolved to "
            f"database={target.database!r} schema={target.schema!r}. "
            "Set them in sqlbuild_project.toml defaults, environment config, or model config.",
            code="S101",
        )
