"""Scope CLI parser and dispatch tests."""

from __future__ import annotations

import sys

import pytest

from sqlbuild.cli.commands._helpers.entry.lazy_handlers import build_lazy_cli_handlers
from sqlbuild.cli.commands.main.entrypoint.entry import _main_with_dependencies
from sqlbuild.cli.commands.models import CliEntrypointHandlers, ScopeCommandRequest
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    ScopeArgumentMisuseCase,
    ScopeEntryCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.entry.helpers import build_handlers


@pytest.mark.parametrize(
    "test_case", (ScopeEntryCase("all_flags", 7),), ids=lambda case: case.description
)
def test_given_all_scope_flags_when_dispatching_then_builds_typed_frozen_request(
    test_case: ScopeEntryCase,
) -> None:
    received: list[ScopeCommandRequest] = []

    def record(request: ScopeCommandRequest) -> int:
        received.append(request)
        return 7

    exit_code: int = _main_with_dependencies(
        argv=(
            "scope",
            "model:orders",
            "--as-path",
            "models/marts/orders.sql",
            "--defined-under",
            "macros/shared/",
            "--kind",
            "macro",
            "--kind",
            "enum",
            "--match",
            "normal*",
            "--used-only",
            "--include-nearby",
            "--nearby-depth",
            "2",
            "--dependency-depth",
            "3",
            "--explain",
            "macro:normalize",
            "--globals",
            "all",
            "--page-size",
            "5",
            "--paths",
            "compact",
            "--json",
            "--no-cache",
        ),
        handlers=build_handlers(run_scope=record),
    )

    assert exit_code == test_case.expected_exit_code
    assert received == [
        ScopeCommandRequest(
            target="model:orders",
            as_path="models/marts/orders.sql",
            defined_under="macros/shared/",
            kinds=("macro", "enum"),
            match="normal*",
            used_only=True,
            include_nearby=True,
            nearby_depth=2,
            dependency_depth=3,
            explain="macro:normalize",
            globals="all",
            page_size=5,
            paths="compact",
            json_output=True,
            no_cache=True,
        )
    ]
    assert ScopeCommandRequest.__dataclass_params__.frozen is True


@pytest.mark.parametrize(
    "test_case",
    (
        ScopeArgumentMisuseCase("missing_target", ("scope",)),
        ScopeArgumentMisuseCase("target_and_at", ("scope", "model:x", "--at", "models/x.sql")),
        ScopeArgumentMisuseCase(
            "move_without_target",
            ("scope", "--at", "models/x.sql", "--as-path", "models/y.sql"),
        ),
        ScopeArgumentMisuseCase("cursor_without_list", ("scope", "model:x", "--after", "macro:x")),
        ScopeArgumentMisuseCase("zero_page", ("scope", "model:x", "--page-size", "0")),
        ScopeArgumentMisuseCase("negative_depth", ("scope", "model:x", "--nearby-depth", "-1")),
        ScopeArgumentMisuseCase(
            "unqualified_explanation", ("scope", "model:x", "--explain", "normalize")
        ),
        ScopeArgumentMisuseCase(
            "browse_with_filter", ("scope", "model:x", "--browse", ".", "--kind", "macro")
        ),
        ScopeArgumentMisuseCase(
            "list_with_report_option",
            ("scope", "model:x", "--list", "global", "--include-nearby"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scope_argument_misuse_when_parsing_then_returns_argparse_exit(
    test_case: ScopeArgumentMisuseCase,
) -> None:
    assert (
        _main_with_dependencies(argv=test_case.argv, handlers=build_handlers())
        == test_case.expected_exit_code
    )


@pytest.mark.parametrize(
    "test_case", (ScopeEntryCase("lazy", 0),), ids=lambda case: case.description
)
def test_given_lazy_handlers_when_built_then_scope_implementation_is_not_imported(
    test_case: ScopeEntryCase,
) -> None:
    sys.modules.pop("sqlbuild.cli.commands.main.inspection._scope", None)

    handlers: CliEntrypointHandlers = build_lazy_cli_handlers()

    assert callable(handlers.run_scope)
    assert "sqlbuild.cli.commands.main.inspection._scope" not in sys.modules
    assert test_case.expected_exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
