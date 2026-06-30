"""Public clone item prephase-row entrypoint."""

from __future__ import annotations

from sqlbuild.executor.clone.helpers.prephase_progress import (
    prephase_row_from_clone_item as _prephase_row_from_clone_item,
)
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.shared.models import PrephaseProgressRow


def prephase_row_from_clone_item(
    *, item: CloneItemResult, caused_by_names: tuple[str, ...]
) -> PrephaseProgressRow:
    """Build a shared prephase row from a clone item result."""

    return _prephase_row_from_clone_item(item=item, caused_by_names=caused_by_names)
