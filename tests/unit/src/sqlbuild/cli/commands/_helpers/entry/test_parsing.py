"""Tests for cross-command CLI output mode normalization."""

from __future__ import annotations

from importlib.metadata import version as installed_version
from pathlib import Path

import pytest

from sqlbuild._native import (
    CompileLineageMode,
    ParsedCliInvocation,
    PlaygroundTemplate,
    parse_cli_invocation,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.scopes.types import DeclarationKind
from tests.unit.src.sqlbuild.cli.commands._helpers.entry._test_types import (
    AuditConcurrencyParsingTestCase,
    ChoiceListTestCase,
    DbtProjectDirParsingTestCase,
    GlobalFlagPlacementTestCase,
    HelpOutputTestCase,
    OutputFormatAliasTestCase,
    PositionalSelectTestCase,
    QueryDiffParsingTestCase,
    RejectedArgumentsTestCase,
    TypedValueTestCase,
    UntypedCursorParsingTestCase,
    VarsRejectionTestCase,
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
        use_color=False,
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
        use_color=False,
    )
    verbose: ParsedCliInvocation = parse_cli_invocation(
        argv=(*test_case.expected_argv, "--verbose"),
        use_color=False,
    )
    debug: ParsedCliInvocation = parse_cli_invocation(
        argv=("--debug", *test_case.expected_argv),
        use_color=False,
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

    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

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
        use_color=False,
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
    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

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
    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

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
    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

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
    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

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
    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

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
            description="undecodable choice is shown escaped",
            argv=("compile", "--lineage-mode", "\udcff"),
            expected_message="argument --lineage-mode: invalid choice: '\\udcff'",
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
    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

    assert parsed.args is None
    assert parsed.exit_code == 2
    assert test_case.expected_message in capsys.readouterr().err


@pytest.mark.parametrize(
    "test_case",
    [
        TypedValueTestCase(
            description="path option",
            argv=("build", "--json-output", "out/run.json"),
            attribute="json_output",
            expected_value=Path("out/run.json"),
        ),
        TypedValueTestCase(
            description="json vars",
            argv=("build", "--vars", '{"region": "emea", "limits": [1, 2]}'),
            attribute="vars",
            expected_value={"region": "emea", "limits": [1, 2]},
        ),
        TypedValueTestCase(
            description="integer option",
            argv=("build", "--concurrency", "3"),
            attribute="concurrency",
            expected_value=3,
        ),
        TypedValueTestCase(
            description="positive integer option",
            argv=("build", "--max-microbatches", "2"),
            attribute="max_microbatches",
            expected_value=2,
        ),
        TypedValueTestCase(
            description="enum namespace default outside compile",
            argv=("build",),
            attribute="compile_lineage_mode",
            expected_value=CompileLineageMode.FAST,
        ),
        TypedValueTestCase(
            description="undecodable selector bytes survive",
            argv=("build", "orders\udcff"),
            attribute="select",
            expected_value=["orders\udcff"],
        ),
        TypedValueTestCase(
            description="compile lineage mode choice is a string",
            argv=("compile", "--lineage-mode", "rich"),
            attribute="compile_lineage_mode",
            expected_value="rich",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_typed_options_when_parsing_then_values_have_their_python_types(
    test_case: TypedValueTestCase,
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

    assert parsed.args is not None
    value: object = getattr(parsed.args, test_case.attribute)
    assert value == test_case.expected_value
    assert type(value) is type(test_case.expected_value)


@pytest.mark.parametrize(
    "test_case",
    [
        ChoiceListTestCase(
            description="compile lineage mode",
            argv=("compile", "--lineage-mode"),
            option="--lineage-mode",
            expected_choices=tuple(mode.value for mode in CompileLineageMode),
        ),
        ChoiceListTestCase(
            description="column lineage mode",
            argv=("lineage", "orders", "--mode"),
            option="--mode",
            expected_choices=tuple(mode.value for mode in ColumnLineageMode),
        ),
        ChoiceListTestCase(
            description="scope declaration kind",
            argv=("scope", "orders", "--kind"),
            option="--kind",
            expected_choices=tuple(kind.value for kind in DeclarationKind),
        ),
        ChoiceListTestCase(
            description="playground template",
            argv=("playground", "--template"),
            option="--template",
            expected_choices=tuple(template.value for template in PlaygroundTemplate),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_choice_when_parsing_then_error_lists_the_python_enum_values(
    test_case: ChoiceListTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=(*test_case.argv, "not-a-choice"), use_color=False
    )

    choices: str = ", ".join(repr(choice) for choice in test_case.expected_choices)
    assert parsed.exit_code == 2
    assert (
        f"argument {test_case.option}: invalid choice: 'not-a-choice' (choose from {choices})"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize(
    "test_case",
    [
        VarsRejectionTestCase(
            description="malformed json",
            vars_value="{orders",
            expected_message="argument --vars: --vars must be valid JSON: Expecting property name",
        ),
        VarsRejectionTestCase(
            description="json array",
            vars_value="[1]",
            expected_message="argument --vars: --vars must be a JSON object",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_vars_when_parsing_then_exits_with_coded_usage_error(
    test_case: VarsRejectionTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=("build", "--vars", test_case.vars_value), use_color=False
    )

    error: str = capsys.readouterr().err
    assert parsed.exit_code == 2
    assert error.startswith("usage: sqb build")
    assert f"sqb build: error[C900]: {test_case.expected_message}" in error


@pytest.mark.parametrize(
    "test_case",
    [
        HelpOutputTestCase(description="root help", argv=("-h",), expected_usage="usage: sqb [-h]"),
        HelpOutputTestCase(
            description="command help", argv=("build", "--help"), expected_usage="usage: sqb build"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_help_flag_when_parsing_then_prints_help_and_exits_zero(
    test_case: HelpOutputTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parsed: ParsedCliInvocation = parse_cli_invocation(argv=test_case.argv, use_color=False)

    output: str = capsys.readouterr().out
    assert parsed.args is None
    assert parsed.exit_code == 0
    assert output.startswith(test_case.expected_usage)
    assert "\noptions:\n" in output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
