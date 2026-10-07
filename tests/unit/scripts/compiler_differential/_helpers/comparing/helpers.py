"""Neutral frontier-like values whose captures share large repeated subtrees."""

from __future__ import annotations

from typing import cast

_LINE_COUNT: int = 40
_ORDER_COUNT: int = 6
_RUN_ID: str = "20261006T172510Z_dee386e8ffa7"
_OTHER_RUN_ID: str = "20261007T081500Z_0a1b2c3d4e5f"
_CHANGED_QUANTITY: int = 99


def orders_batch() -> dict[str, object]:
    """Return orders that repeat two identical large orders."""

    return {
        "run_id": _RUN_ID,
        "orders": [_order(order_id=index % 2) for index in range(_ORDER_COUNT)],
    }


def orders_batch_with_changed_line(*, order_index: int, line_index: int) -> dict[str, object]:
    """Return the repeated orders with one quantity of one order changed."""

    batch: dict[str, object] = orders_batch()
    orders: list[dict[str, object]] = cast(list[dict[str, object]], batch["orders"])
    lines: list[dict[str, object]] = cast(list[dict[str, object]], orders[order_index]["lines"])
    lines[line_index]["quantity"] = _CHANGED_QUANTITY
    return batch


def orders_batch_for_run() -> dict[str, object]:
    """Return the repeated orders, each recording the default run id."""

    return _orders_recording(run_id=_RUN_ID)


def orders_batch_from_other_run() -> dict[str, object]:
    """Return the same orders, each recording a different run id."""

    return _orders_recording(run_id=_OTHER_RUN_ID)


def _orders_recording(*, run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "orders": [
            {**_order(order_id=index % 2), "run_id": run_id} for index in range(_ORDER_COUNT)
        ],
    }


def _order(*, order_id: int) -> dict[str, object]:
    return {"order_id": order_id, "lines": _order_lines()}


def _order_lines() -> list[dict[str, object]]:
    return [{"sku": f"product-{line:04d}", "quantity": line} for line in range(_LINE_COUNT)]


def store_paths(*, native_suffix: str) -> dict[str, object]:
    """Return a set of two large store paths, one carrying an engine namespace suffix."""

    return {"paths": frozenset({"a" * 1100 + f"/store{native_suffix}", "b" * 1100})}


def marker_shaped_orders(*, name: str) -> dict[str, object]:
    """Return authored data whose only key looks like a shared-node reference marker."""

    return {"__shared__": name}


def orders_batch_without_last() -> dict[str, object]:
    """Return the repeated orders with the last one removed."""

    batch: dict[str, object] = orders_batch()
    orders: list[dict[str, object]] = cast(list[dict[str, object]], batch["orders"])
    batch["orders"] = orders[:-1]
    return batch
