"""Per-model full-refresh resolution."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.planner.constants import FULL_REFRESH_DISABLED_REBUILD_CODE
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import ChangeDetectionResult
from sqlbuild.compiler.planner.types import ChangeKind


def resolve_model_full_refresh(*, model: CompiledModel, cli_full_refresh: bool) -> bool:
    """Resolve dbt-compatible nullable model full-refresh semantics."""

    configured: object | None = model.config.values.get("full_refresh")
    return configured if isinstance(configured, bool) else cli_full_refresh


def effectively_full_refreshed_model_names(
    *, project: CompiledProject, cli_full_refresh: bool
) -> frozenset[str]:
    """Return model names that are effectively full refreshed for this invocation."""

    return frozenset(
        model.name
        for model in project.models
        if resolve_model_full_refresh(model=model, cli_full_refresh=cli_full_refresh)
    )


def describe_full_rebuild_cause(*, change_result: ChangeDetectionResult, full_refresh: bool) -> str:
    """Describe why an incremental model is planned as a full rebuild."""

    if full_refresh:
        return "--full-refresh"
    if change_result.change_kind == ChangeKind.FIRST_RUN:
        return "first run"
    if change_result.change_kind == ChangeKind.RENAMED:
        return "rename"
    if change_result.query_changed:
        return "query changed with replay_on_change full"
    if change_result.changed_functions:
        names: str = ", ".join(change_result.changed_functions)
        return f"function {names} changed with replay_on_change full"
    if change_result.schema_findings:
        return "schema changed with replay_on_change full"
    return "full backfill"


def check_full_rebuild_allowed(
    *, model: CompiledModel, change_result: ChangeDetectionResult, full_rebuild_cause: str
) -> None:
    """Refuse a full rebuild of a full_refresh false model unless its own SQL or first run asks."""

    if model.config.values.get("full_refresh") is not False:
        return
    if change_result.change_kind == ChangeKind.FIRST_RUN or change_result.query_changed:
        return
    raise PlannerInputError(
        f"model '{model.name}' sets full_refresh false, but the plan would fully rebuild it "
        f"({full_rebuild_cause})",
        code=FULL_REFRESH_DISABLED_REBUILD_CODE,
        help=(
            "set replay_on_change to forward or bounded-<duration> on this model to keep its "
            "existing history, or remove full_refresh false to allow the rebuild"
        ),
    )
