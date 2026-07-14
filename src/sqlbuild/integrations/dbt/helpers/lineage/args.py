"""Argument parsing for mixed dbt/SQLBuild lineage."""

from __future__ import annotations

from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.helpers.lineage.constants import (
    DBT_LINEAGE_DEPTH_ALL,
    DBT_LINEAGE_DEPTH_FLAG,
    DBT_LINEAGE_DIRECTION_FLAG,
    DBT_LINEAGE_FORMAT_FLAG,
    DBT_LINEAGE_NO_SQL_VALIDATION_FLAG,
)
from sqlbuild.integrations.dbt.models import DbtLineageArgs
from sqlbuild.integrations.dbt.types import DbtLineageDirection, DbtLineageOutputFormat


def parse_dbt_lineage_args(args: tuple[str, ...]) -> DbtLineageArgs:
    """Parse `sqb dbt lineage` arguments."""

    target: str | None = None
    output_format: DbtLineageOutputFormat = DbtLineageOutputFormat.TREE
    direction: DbtLineageDirection = DbtLineageDirection.UPSTREAM
    raw_depth: str = DBT_LINEAGE_DEPTH_ALL
    no_sql_validation: bool = False
    dbt_args: list[str] = []
    index: int = 0
    while index < len(args):
        token: str = args[index]
        if token == DBT_LINEAGE_FORMAT_FLAG:
            raw_output_format: str
            raw_output_format, index = _consume_lineage_value(args=args, index=index)
            try:
                output_format = DbtLineageOutputFormat(raw_output_format)
            except ValueError as exc:
                raise DbtInteropArgumentError(
                    "--format must be tree, json, or list", code="C334"
                ) from exc
            continue
        if token == DBT_LINEAGE_DIRECTION_FLAG:
            raw_direction: str
            raw_direction, index = _consume_lineage_value(args=args, index=index)
            try:
                direction = DbtLineageDirection(raw_direction)
            except ValueError as exc:
                raise DbtInteropArgumentError(
                    "--direction must be upstream, downstream, or both", code="C335"
                ) from exc
            continue
        if token == DBT_LINEAGE_DEPTH_FLAG:
            raw_depth, index = _consume_lineage_value(args=args, index=index)
            continue
        if token == DBT_LINEAGE_NO_SQL_VALIDATION_FLAG:
            no_sql_validation = True
            index += 1
            continue
        if token.startswith("--"):
            dbt_args.append(token)
            if index + 1 < len(args) and not args[index + 1].startswith("--"):
                dbt_args.append(args[index + 1])
                index += 2
            else:
                index += 1
            continue
        if target is not None:
            raise DbtInteropArgumentError(
                "dbt lineage accepts exactly one lineage target resource", code="C332"
            )
        target = token
        index += 1
    if target is None:
        raise DbtInteropArgumentError(
            "dbt lineage requires a lineage target resource, for example: "
            "sqb dbt lineage dbt_orders",
            code="C333",
        )
    return DbtLineageArgs(
        target=target,
        output_format=output_format,
        direction=direction,
        depth=_parse_depth(raw_depth),
        no_sql_validation=no_sql_validation,
        dbt_args=tuple(dbt_args),
    )


def _consume_lineage_value(*, args: tuple[str, ...], index: int) -> tuple[str, int]:
    if index + 1 >= len(args) or args[index + 1].startswith("--"):
        raise DbtInteropArgumentError(f"{args[index]} requires a value", code="C235")
    return args[index + 1], index + 2


def _parse_depth(raw_depth: str) -> int | None:
    if raw_depth == DBT_LINEAGE_DEPTH_ALL:
        return None
    try:
        depth: int = int(raw_depth)
    except ValueError:
        raise DbtInteropArgumentError(
            "--depth must be a non-negative integer or 'all'", code="C304"
        ) from None
    if depth < 0:
        raise DbtInteropArgumentError(
            "--depth must be a non-negative integer or 'all'", code="C304"
        )
    return depth
