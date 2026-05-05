"""Function fingerprint source helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    FunctionArgument,
    FunctionReturnColumn,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import BackfillResult, WarehouseSnapshot
from sqlbuild.compiler.planner.types import BackfillAction
from sqlbuild.compiler.shared.helpers.hashing import compute_query_hash


def build_compiled_function_fingerprint_sql(function: CompiledFunction) -> str:
    """Build stable function definition text used for change fingerprints."""

    return build_function_fingerprint_sql(
        name=function.name,
        target_database=function.target.database,
        target_schema=function.target.schema,
        target_name=function.target.name,
        arguments=function.arguments,
        returns=function.returns,
        return_columns=function.return_columns,
        body_sql=function.body_sql,
        language=str(function.language),
        runtime_version=function.runtime_version,
        entry_point=function.entry_point,
        packages=function.packages,
    )


def detect_function_backfill(
    *,
    function: CompiledFunction,
    fingerprint_sql: str,
    snapshot: WarehouseSnapshot,
    query_change_tracking: bool,
    full_refresh: bool,
) -> BackfillResult:
    """Resolve a function definition change into a cascadeable backfill."""

    if full_refresh:
        return BackfillResult(action=BackfillAction.FULL)
    fingerprint: Fingerprint | None = snapshot.fingerprints.get(function.name)
    if fingerprint is None:
        return BackfillResult(action=BackfillAction.FULL)
    if not query_change_tracking:
        return BackfillResult(action=BackfillAction.WARN_ONLY)
    if compute_query_hash(fingerprint_sql) != fingerprint.query_hash:
        return BackfillResult(action=BackfillAction.FULL)
    return BackfillResult(action=BackfillAction.WARN_ONLY)


def build_function_fingerprint_sql(
    *,
    name: str,
    target_database: str | None,
    target_schema: str | None,
    target_name: str,
    arguments: tuple[FunctionArgument | object, ...],
    returns: str,
    body_sql: str,
    language: str,
    runtime_version: str | None,
    entry_point: str | None,
    packages: tuple[str, ...],
    return_columns: tuple[FunctionReturnColumn | object, ...] = (),
) -> str:
    """Build stable function definition text used for change fingerprints."""

    rendered_arguments: str = ",".join(_render_argument(arg) for arg in arguments)
    rendered_return_columns: str = ",".join(
        _render_return_column(column) for column in return_columns
    )
    rendered_packages: str = ",".join(packages)
    return "\n".join(
        (
            f"name={name}",
            f"target_database={target_database or ''}",
            f"target_schema={target_schema or ''}",
            f"target_name={target_name}",
            f"language={language}",
            f"arguments={rendered_arguments}",
            f"returns={returns}",
            f"return_columns={rendered_return_columns}",
            f"runtime_version={runtime_version or ''}",
            f"entry_point={entry_point or ''}",
            f"packages={rendered_packages}",
            "body=",
            body_sql,
        )
    )


def _render_argument(argument: FunctionArgument | object) -> str:
    name: object | None = getattr(argument, "name", None)
    arg_type: object | None = getattr(argument, "type", None)
    return f"{name or ''}:{arg_type or ''}"


def _render_return_column(column: FunctionReturnColumn | object) -> str:
    name: object | None = getattr(column, "name", None)
    col_type: object | None = getattr(column, "type", None)
    return f"{name or ''}:{col_type or ''}"
