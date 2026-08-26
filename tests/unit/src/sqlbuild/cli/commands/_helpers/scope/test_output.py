"""Scope browse and list text presentation tests."""

from __future__ import annotations

from io import StringIO

import pytest

from sqlbuild.cli.commands._helpers.scope.command import run_scope_command
from sqlbuild.cli.commands.models import ScopeCommandRequest
from tests.unit.src.sqlbuild.cli.commands._helpers.scope._test_types import ScopeOutputCase
from tests.unit.src.sqlbuild.compiler.scopes.helpers import report_scope_lookup


@pytest.mark.parametrize(
    "test_case", (ScopeOutputCase("browse", 0),), ids=lambda case: case.description
)
def test_given_browse_result_when_rendering_then_counts_and_follow_ups_are_exact(
    test_case: ScopeOutputCase,
) -> None:
    stream: StringIO = StringIO()

    exit_code: int = run_scope_command(
        request=ScopeCommandRequest(target="model:orders", browse="global"),
        load_scope_index=lambda **_kwargs: report_scope_lookup().index,
        output_stream=stream,
    )

    assert exit_code == test_case.expected_exit_code
    assert "Scope folders" in stream.getvalue()
    assert "declarations" in stream.getvalue()
    assert "sqb scope model:orders --browse" in stream.getvalue()
    assert "sqb scope model:orders --list" in stream.getvalue()


@pytest.mark.parametrize(
    "test_case", (ScopeOutputCase("list", 0),), ids=lambda case: case.description
)
def test_given_paginated_list_when_rendering_then_continuation_repeats_filters(
    test_case: ScopeOutputCase,
) -> None:
    stream: StringIO = StringIO()
    request: ScopeCommandRequest = ScopeCommandRequest(
        target="model:orders",
        list_path="global/constants",
        kinds=("constant",),
        match="global_*",
        page_size=1,
        no_cache=True,
    )

    exit_code: int = run_scope_command(
        request=request,
        load_scope_index=lambda **_kwargs: report_scope_lookup(extra_globals=3).index,
        output_stream=stream,
    )

    assert exit_code == test_case.expected_exit_code
    assert (
        "Continue: sqb scope model:orders --list global/constants --kind constant "
        "--match 'global_*' --page-size 1 --after constant:global_00000 --no-cache"
        in stream.getvalue()
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
