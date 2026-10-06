"""Tests for cross-command CLI output mode normalization."""

from __future__ import annotations

from importlib.metadata import version as installed_version

import pytest

from sqlbuild.cli.commands._helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands._helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.entry.models import (
    ParsedCliInvocation,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.entry._test_types import (
    AuditConcurrencyParsingTestCase,
    DbtProjectDirParsingTestCase,
    GlobalFlagPlacementTestCase,
    OutputFormatAliasTestCase,
    PositionalSelectTestCase,
    QueryDiffParsingTestCase,
    RejectedArgumentsTestCase,
    UntypedCursorParsingTestCase,
    VerboseCommandTestCase,
    VersionFlagTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        QueryDiffParsingTestCase(
            description="inline composite keyed query diff",
            argv=(
                "diff",
                "--left-query",
                "SELECT order_id FROM old_orders",
                "--right-query",
                "SELECT order_id FROM new_orders",
                "--key",
                "account_id",
                "--key",
                "order_id",
            ),
            expected_left_query="SELECT order_id FROM old_orders",
            expected_right_query="SELECT order_id FROM new_orders",
            expected_keys=("account_id", "order_id"),
            expected_unkeyed=False,
        ),
        QueryDiffParsingTestCase(
            description="inline unkeyed query diff",
            argv=(
                "diff",
                "--left-query",
                "VALUES (1)",
                "--right-query",
                "VALUES (1)",
                "--unkeyed",
            ),
            expected_left_query="VALUES (1)",
            expected_right_query="VALUES (1)",
            expected_keys=(),
            expected_unkeyed=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_raw_query_diff_arguments_when_parsing_then_inputs_remain_distinct(
    test_case: QueryDiffParsingTestCase,
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv,
        parser=build_cli_parser(),
    )

    assert parsed.args is not None
    assert parsed.args.target_range is None
    assert parsed.args.left_query == test_case.expected_left_query
    assert parsed.args.right_query == test_case.expected_right_query
    assert tuple(parsed.args.key) == test_case.expected_keys
    assert parsed.args.unkeyed is test_case.expected_unkeyed


@pytest.mark.parametrize(
    "test_case",
    [
        VerboseCommandTestCase(description="plan", expected_argv=("plan",)),
        VerboseCommandTestCase(description="build", expected_argv=("build",)),
        VerboseCommandTestCase(
            description="clone",
            expected_argv=("clone", "--from", "prod", "--to", "dev"),
        ),
        VerboseCommandTestCase(description="diff", expected_argv=("diff", "prod:dev")),
    ],
    ids=lambda case: case.description,
)
def test_given_output_mode_when_parsing_verbose_command_then_normalizes_consistently(
    test_case: VerboseCommandTestCase,
) -> None:
    default: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.expected_argv,
        parser=build_cli_parser(),
    )
    verbose: ParsedCliInvocation = parse_cli_invocation(
        argv=(*test_case.expected_argv, "--verbose"),
        parser=build_cli_parser(),
    )
    debug: ParsedCliInvocation = parse_cli_invocation(
        argv=("--debug", *test_case.expected_argv),
        parser=build_cli_parser(),
    )

    assert default.args is not None
    assert verbose.args is not None
    assert debug.args is not None
    assert (default.args.verbose, default.args.debug) == (False, False)
    assert (verbose.args.verbose, verbose.args.debug) == (True, False)
    assert (debug.args.verbose, debug.args.debug) == (True, True)


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyParsingTestCase(
            description="cli wins over environment",
            argv=("audit", "--concurrency", "3"),
            environment_value="7",
            expected_concurrency=3,
            expected_exit_code=None,
        ),
        AuditConcurrencyParsingTestCase(
            description="environment fallback",
            argv=("audit",),
            environment_value="7",
            expected_concurrency=7,
            expected_exit_code=None,
        ),
        AuditConcurrencyParsingTestCase(
            description="test command cli override",
            argv=("test", "--concurrency", "5"),
            environment_value=None,
            expected_concurrency=5,
            expected_exit_code=None,
        ),
        AuditConcurrencyParsingTestCase(
            description="zero cli rejected",
            argv=("audit", "--concurrency", "0"),
            environment_value=None,
            expected_concurrency=None,
            expected_exit_code=2,
        ),
        AuditConcurrencyParsingTestCase(
            description="negative cli rejected",
            argv=("audit", "--concurrency", "-1"),
            environment_value=None,
            expected_concurrency=None,
            expected_exit_code=2,
        ),
        AuditConcurrencyParsingTestCase(
            description="zero environment rejected",
            argv=("audit",),
            environment_value="0",
            expected_concurrency=None,
            expected_exit_code=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_audit_concurrency_sources_when_parsing_then_precedence_and_validation_apply(
    test_case: AuditConcurrencyParsingTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLBUILD_CONCURRENCY", test_case.environment_value or "")

    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.exit_code == test_case.expected_exit_code
    assert getattr(parsed.args, "concurrency", None) == test_case.expected_concurrency


@pytest.mark.parametrize(
    "test_case",
    [
        VersionFlagTestCase(
            description="long flag exits zero without a project",
            argv=("--version",),
            expected_exit_code=0,
        ),
        VersionFlagTestCase(
            description="short flag exits zero without a project",
            argv=("-V",),
            expected_exit_code=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_version_flag_when_parsing_then_prints_version_and_exits_zero(
    test_case: VersionFlagTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invocation: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv,
        parser=build_cli_parser(),
    )

    assert invocation.args is None
    assert invocation.exit_code == test_case.expected_exit_code
    assert f"sqb {installed_version('sqlbuild')}" in capsys.readouterr().out


@pytest.mark.parametrize(
    "test_case",
    [
        GlobalFlagPlacementTestCase(
            description="before the subcommand",
            argv=("--debug", "--no-color", "--project-dir", "shop", "build"),
            expected_debug=True,
            expected_no_color=True,
            expected_project_dir="shop",
        ),
        GlobalFlagPlacementTestCase(
            description="after the subcommand",
            argv=("build", "--debug", "--no-color", "--project-dir", "shop"),
            expected_debug=True,
            expected_no_color=True,
            expected_project_dir="shop",
        ),
        GlobalFlagPlacementTestCase(
            description="legacy project dir alias after the subcommand",
            argv=("compile", "--sqb-project-dir", "shop"),
            expected_debug=False,
            expected_no_color=False,
            expected_project_dir="shop",
        ),
        GlobalFlagPlacementTestCase(
            description="root values survive an unflagged subcommand",
            argv=("--debug", "--project-dir", "shop", "plan", "--no-color"),
            expected_debug=True,
            expected_no_color=True,
            expected_project_dir="shop",
        ),
        GlobalFlagPlacementTestCase(
            description="after a nested subcommand",
            argv=("contract", "diff", "--from", "prod", "--debug", "--project-dir", "shop"),
            expected_debug=True,
            expected_no_color=False,
            expected_project_dir="shop",
        ),
        GlobalFlagPlacementTestCase(
            description="omitted everywhere",
            argv=("test",),
            expected_debug=False,
            expected_no_color=False,
            expected_project_dir=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_global_flags_anywhere_when_parsing_then_they_apply_to_the_invocation(
    test_case: GlobalFlagPlacementTestCase,
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.args is not None
    assert parsed.args.debug is test_case.expected_debug
    assert parsed.args.no_color is test_case.expected_no_color
    assert parsed.args.project_dir == test_case.expected_project_dir


@pytest.mark.parametrize(
    "test_case",
    [
        DbtProjectDirParsingTestCase(
            description="dbt init keeps its own project dir",
            argv=("dbt", "init", "--project-dir", "dbt_shop"),
            expected_dbt_project_dir="dbt_shop",
            expected_dbt_args=(),
            expected_no_color=False,
        ),
        DbtProjectDirParsingTestCase(
            description="dbt passthrough still receives project dir",
            argv=("dbt", "build", "--no-color", "--project-dir", "dbt_shop"),
            expected_dbt_project_dir=None,
            expected_dbt_args=("--project-dir", "dbt_shop"),
            expected_no_color=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_project_dir_when_parsing_then_it_is_not_the_sqlbuild_project_dir(
    test_case: DbtProjectDirParsingTestCase,
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.args is not None
    assert parsed.args.project_dir is None
    assert parsed.args.dbt_project_dir == test_case.expected_dbt_project_dir
    assert tuple(parsed.args.dbt_args) == test_case.expected_dbt_args
    assert parsed.args.no_color is test_case.expected_no_color


@pytest.mark.parametrize(
    "test_case",
    [
        PositionalSelectTestCase(
            description="build graph selector",
            argv=("build", "stg_orders+"),
            expected_select=("stg_orders+",),
        ),
        PositionalSelectTestCase(
            description="positional and select are combined",
            argv=("plan", "stg_orders", "--select", "dim_customers"),
            expected_select=("stg_orders", "dim_customers"),
        ),
        PositionalSelectTestCase(
            description="selectors on both sides of an option",
            argv=("build", "stg_orders", "--full-refresh", "tag:daily"),
            expected_select=("stg_orders", "tag:daily"),
        ),
        PositionalSelectTestCase(
            description="compile",
            argv=("compile", "+fact_orders"),
            expected_select=("+fact_orders",),
        ),
        PositionalSelectTestCase(
            description="test", argv=("test", "stg_orders"), expected_select=("stg_orders",)
        ),
        PositionalSelectTestCase(
            description="seed", argv=("seed", "waffle_types"), expected_select=("waffle_types",)
        ),
        PositionalSelectTestCase(
            description="freshness",
            argv=("freshness", "source:raw__orders"),
            expected_select=("source:raw__orders",),
        ),
        PositionalSelectTestCase(
            description="audit", argv=("audit", "fact_orders"), expected_select=("fact_orders",)
        ),
        PositionalSelectTestCase(
            description="check", argv=("check", "fact_orders"), expected_select=("fact_orders",)
        ),
        PositionalSelectTestCase(
            description="select only", argv=("build", "-s", "a", "b"), expected_select=("a", "b")
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_positional_selectors_when_parsing_then_they_join_the_selection(
    test_case: PositionalSelectTestCase,
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.args is not None
    assert tuple(parsed.args.select) == test_case.expected_select


@pytest.mark.parametrize(
    "test_case",
    [
        OutputFormatAliasTestCase(
            description="lineage json",
            argv=("lineage", "stg_orders", "--json"),
            format_attribute="lineage_format",
            expected_format="json",
        ),
        OutputFormatAliasTestCase(
            description="lineage default",
            argv=("lineage", "stg_orders"),
            format_attribute="lineage_format",
            expected_format="tree",
        ),
        OutputFormatAliasTestCase(
            description="query json",
            argv=("query", "SELECT 1", "--json"),
            format_attribute="query_format",
            expected_format="json",
        ),
        OutputFormatAliasTestCase(
            description="query explicit format",
            argv=("query", "SELECT 1", "--format", "csv"),
            format_attribute="query_format",
            expected_format="csv",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_json_alias_when_parsing_then_selects_json_format(
    test_case: OutputFormatAliasTestCase,
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.args is not None
    assert getattr(parsed.args, test_case.format_attribute) == test_case.expected_format
    assert parsed.args.json is False


@pytest.mark.parametrize(
    "test_case",
    [
        UntypedCursorParsingTestCase(
            description="load keeps untyped values raw",
            argv=("load", "--start-cursor", "2026-05-01", "--end-cursor", "2026-05-02"),
            expected_start="2026-05-01",
            expected_end="2026-05-02",
        ),
        UntypedCursorParsingTestCase(
            description="build accepts start only",
            argv=("build", "--start-cursor", "100"),
            expected_start="100",
            expected_end=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_untyped_cursor_flags_when_parsing_then_values_are_kept_raw(
    test_case: UntypedCursorParsingTestCase,
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.args is not None
    assert (parsed.args.start_cursor, parsed.args.end_cursor) == (
        test_case.expected_start,
        test_case.expected_end,
    )
    assert parsed.args.start_cursor_ts is None


@pytest.mark.parametrize(
    "test_case",
    [
        RejectedArgumentsTestCase(
            description="unknown option among selectors",
            argv=("build", "stg_orders", "--no-such-flag", "fact_orders"),
            expected_message="unrecognized arguments: --no-such-flag fact_orders",
        ),
        RejectedArgumentsTestCase(
            description="positional on a command without positional selection",
            argv=("load", "raw__orders"),
            expected_message="unrecognized arguments: raw__orders",
        ),
        RejectedArgumentsTestCase(
            description="json alias with an explicit format",
            argv=("lineage", "stg_orders", "--json", "--format", "tree"),
            expected_message="argument --format: not allowed with argument --json",
        ),
        RejectedArgumentsTestCase(
            description="untyped and typed cursor flags together",
            argv=("build", "--start-cursor", "5", "--end-cursor-int", "9"),
            expected_message=(
                "--start-cursor/--end-cursor cannot be combined with the -ts or -int cursor flags"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_or_unknown_arguments_when_parsing_then_exits_with_usage_error(
    test_case: RejectedArgumentsTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.args is None
    assert parsed.exit_code == 2
    assert test_case.expected_message in capsys.readouterr().err


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
