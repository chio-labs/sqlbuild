"""Metadata size guard for default full model comparisons."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationRowCountEstimate
from sqlbuild.executor.diff._helpers.selection import qualified_name
from sqlbuild.executor.diff.exceptions import FullDiffSizeGuardError
from sqlbuild.executor.diff.models import FullDiffModelSize, FullDiffSideSize, FullDiffSizeLimits
from sqlbuild.spec.contracts.main.get_config_str import get_config_str


def enforce_full_diff_size_limits(
    *,
    adapter: BaseAdapter,
    connection: Any,
    model_pairs: tuple[tuple[str, Any, Any], ...],
    limits: FullDiffSizeLimits,
) -> None:
    """Stop before reading data when any side is over its limit or has an unknown size."""

    sizes: tuple[FullDiffModelSize, ...] = tuple(
        FullDiffModelSize(
            name=name,
            left=_side_size(
                adapter=adapter,
                connection=connection,
                model=left_model,
                target=limits.left_target,
                max_rows=limits.left_max_rows,
            ),
            right=_side_size(
                adapter=adapter,
                connection=connection,
                model=right_model,
                target=limits.right_target,
                max_rows=limits.right_max_rows,
            ),
            has_cursor=get_config_str(values=right_model.config.values, key="cursor") is not None,
        )
        for name, left_model, right_model in model_pairs
    )
    blocked: tuple[FullDiffModelSize, ...] = tuple(size for size in sizes if size.exceeds_limit)
    if blocked:
        raise FullDiffSizeGuardError(
            f"full diff stopped before reading data: {len(blocked)} of {len(sizes)} "
            "selected models exceed the full-comparison row limit or have an unknown size",
            blocked=blocked,
        )


def _side_size(
    *,
    adapter: BaseAdapter,
    connection: Any,
    model: Any,
    target: str,
    max_rows: int | None,
) -> FullDiffSideSize:
    relation: str = qualified_name(adapter=adapter, model=model)
    if max_rows is None:
        return FullDiffSideSize(target=target, relation=relation, row_count=None, max_rows=None)
    estimate: RelationRowCountEstimate = _estimate_row_count(
        adapter=adapter, connection=connection, model=model
    )
    return FullDiffSideSize(
        target=target,
        relation=relation,
        row_count=estimate.row_count,
        max_rows=max_rows,
        detail=estimate.detail,
    )


def _estimate_row_count(
    *, adapter: BaseAdapter, connection: Any, model: Any
) -> RelationRowCountEstimate:
    try:
        return adapter.estimate_relation_row_count(
            connection=connection,
            database=model.destination.database,
            schema=model.destination.schema,
            name=model.destination.name,
        )
    except Exception as error:
        return RelationRowCountEstimate(row_count=None, detail=f"metadata lookup failed: {error}")
