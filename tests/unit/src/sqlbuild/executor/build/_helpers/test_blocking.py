from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.executor.build._helpers.blocking import downstream_blocked_keys
from tests.unit.src.sqlbuild.executor.build._helpers._test_types import (
    DownstreamBlockedKeysTestCase,
)
from tests.unit.src.sqlbuild.executor.build._helpers.helpers import (
    build_model_key_edges,
    model_key,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DownstreamBlockedKeysTestCase(
            description="blocks selected transitive downstreams but not the failed key",
            failed_name="stg_orders",
            downstream_deps={
                "stg_orders": ("orders_summary", "orders_audit"),
                "orders_summary": ("orders_report",),
                "orders_audit": (),
                "orders_report": (),
                "customers": ("orders_report",),
            },
            selected_names=frozenset(
                {"stg_orders", "orders_summary", "orders_audit", "orders_report", "customers"}
            ),
            expected_names=frozenset({"orders_summary", "orders_audit", "orders_report"}),
        ),
        DownstreamBlockedKeysTestCase(
            description="walks through unselected keys to selected descendants",
            failed_name="stg_orders",
            downstream_deps={
                "stg_orders": ("orders_summary",),
                "orders_summary": ("orders_report",),
                "orders_report": (),
            },
            selected_names=frozenset({"stg_orders", "orders_report"}),
            expected_names=frozenset({"orders_report"}),
        ),
        DownstreamBlockedKeysTestCase(
            description="blocks a diamond descendant once",
            failed_name="stg_orders",
            downstream_deps={
                "stg_orders": ("orders_left", "orders_right"),
                "orders_left": ("orders_joined",),
                "orders_right": ("orders_joined",),
                "orders_joined": (),
            },
            selected_names=frozenset({"orders_left", "orders_right", "orders_joined"}),
            expected_names=frozenset({"orders_left", "orders_right", "orders_joined"}),
        ),
        DownstreamBlockedKeysTestCase(
            description="returns nothing for a failed leaf",
            failed_name="orders_report",
            downstream_deps={"stg_orders": ("orders_report",), "orders_report": ()},
            selected_names=frozenset({"stg_orders", "orders_report"}),
            expected_names=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failed_key_when_computing_blocked_keys_then_returns_selected_descendants(
    test_case: DownstreamBlockedKeysTestCase,
) -> None:
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_model_key_edges(
        edges=test_case.downstream_deps
    )

    blocked: frozenset[CompiledObjectKey] = downstream_blocked_keys(
        failed_key=model_key(test_case.failed_name),
        downstream_deps=downstream_deps,
        selected_keys=frozenset(model_key(name) for name in test_case.selected_names),
    )

    assert blocked == frozenset(model_key(name) for name in test_case.expected_names)
