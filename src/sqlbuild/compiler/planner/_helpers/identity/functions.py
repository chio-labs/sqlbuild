"""Function fingerprint source helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    FunctionArgument,
    FunctionReturnColumn,
)
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.identity.hashing import function_definition_hash
from sqlbuild.compiler.planner.types import PlanReason


def build_compiled_function_fingerprint_sql(function: CompiledFunction) -> str:
    """Build stable function definition text used for change fingerprints."""

    return build_function_fingerprint_sql(
        arguments=function.arguments,
        returns=function.returns,
        return_columns=function.return_columns,
        body_sql=function.body_sql,
        language=str(function.language),
        runtime_version=function.runtime_version,
        entry_point=function.entry_point,
        packages=function.packages,
    )


def detect_function_change(
    *,
    function: CompiledFunction,
    fingerprint_sql: str,
    fingerprint: Fingerprint | None,
    query_change_tracking: bool,
    full_refresh: bool,
    dialect: str | None,
) -> PlanReason:
    """Resolve why a function is redeployed; callers decide their own replay."""

    if full_refresh:
        return PlanReason.FULL_REFRESH
    if fingerprint is None:
        return PlanReason.FIRST_RUN
    if query_change_tracking and (
        function_definition_hash(
            function_name=function.name,
            fingerprint_sql=fingerprint_sql,
            language=str(function.language),
            dialect=dialect,
        )
        != fingerprint.definition_hash
    ):
        return PlanReason.QUERY_CHANGED
    return PlanReason.NO_CHANGE


def build_function_fingerprint_sql(
    *,
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
