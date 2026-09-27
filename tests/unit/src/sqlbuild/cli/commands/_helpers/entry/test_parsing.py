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
    QueryDiffParsingTestCase,
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
