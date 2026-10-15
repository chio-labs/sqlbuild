"""Bare scope target qualification tests."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild._native import ScopeCommandRequest, run_scope_command
from sqlbuild.cli.commands.exceptions import CliUserError
from tests.unit.src.sqlbuild.cli.commands._helpers.scope._test_types import (
    ScopeTargetCase,
    ScopeTargetErrorCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.scope.helpers import bare_target_scope_index


@pytest.mark.parametrize(
    "test_case",
    (
        ScopeTargetCase("bare model", "orders", "model:orders"),
        ScopeTargetCase("bare source", "raw__orders", "source:raw__orders"),
        ScopeTargetCase("bare seed", "waffle_types", "seed:waffle_types"),
        ScopeTargetCase(
            "bare function", "udf__is_completed_order", "function:udf__is_completed_order"
        ),
        ScopeTargetCase("prefixed model unchanged", "model:orders", "model:orders"),
    ),
    ids=lambda case: case.description,
)
def test_given_scope_target_when_qualifying_then_bare_resources_gain_their_kind(
    test_case: ScopeTargetCase,
) -> None:
    stream: StringIO = StringIO()
    _ = run_scope_command(
        request=ScopeCommandRequest(target=test_case.target),
        load_scope_index=bare_target_scope_index,
        output_stream=stream,
    )

    assert f"  Target: {test_case.expected_target}\n" in stream.getvalue()


@pytest.mark.parametrize(
    "test_case",
    (
        ScopeTargetErrorCase(
            "bare enum needs prefix",
            "order_status",
            "scope target 'order_status' needs its prefix: enum:order_status",
        ),
        ScopeTargetErrorCase(
            "bare constant needs prefix",
            "warehouse_password",
            "scope target 'warehouse_password' needs its prefix: constant:warehouse_password",
        ),
        ScopeTargetErrorCase(
            "bare test needs prefix",
            "orders_are_unique",
            "scope target 'orders_are_unique' needs its prefix: test:orders_are_unique",
        ),
        ScopeTargetErrorCase(
            "bare model colliding with a macro",
            "normalize",
            "scope target 'normalize' matches more than one resource or declaration; "
            "write model:normalize or macro:normalize",
        ),
        ScopeTargetErrorCase("unknown bare name", "missing", "unknown scope target 'missing'"),
    ),
    ids=lambda case: case.description,
)
def test_given_ambiguous_or_prefix_only_bare_name_when_qualifying_then_raises_clear_error(
    test_case: ScopeTargetErrorCase,
) -> None:
    with pytest.raises(CliUserError) as error:
        _ = run_scope_command(
            request=ScopeCommandRequest(target=test_case.target),
            load_scope_index=bare_target_scope_index,
            output_stream=StringIO(),
        )

    assert error.value.code == "C960"
    assert error.value.message == test_case.expected_message
    assert "macro:<name>" in (error.value.help or "")


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
