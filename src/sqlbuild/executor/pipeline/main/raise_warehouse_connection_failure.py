"""Public entry for the coded failure of a warehouse connection a command cannot open."""

from __future__ import annotations

from typing import NoReturn

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.pipeline.constants import SQLBUILD_PACKAGE
from sqlbuild.executor.pipeline.exceptions import WarehouseConnectionError


def raise_warehouse_connection_failure(*, adapter: BaseAdapter, error: BaseException) -> NoReturn:
    """Raise the coded connection error for `error`, or `error` itself when SQLBuild coded it."""

    if not isinstance(error, Exception) or _is_sqlbuild_coded(error):
        raise error
    raise WarehouseConnectionError(
        adapter_name=getattr(adapter, "adapter_name", None) or type(adapter).__name__,
        reason=str(error) or type(error).__name__,
    ) from error


def _is_sqlbuild_coded(error: Exception) -> bool:
    package: str = type(error).__module__.partition(".")[0]
    return package == SQLBUILD_PACKAGE and isinstance(getattr(error, "code", None), str)
