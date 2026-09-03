"""Tests for cross-command CLI output mode normalization."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands._helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.commands.models import ParsedCliInvocation
from tests.unit.src.sqlbuild.cli.commands._helpers.entry._test_types import (
    AuditConcurrencyParsingTestCase,
    VerboseCommandTestCase,
)


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
        VerboseCommandTestCase(
            description="promote",
            expected_argv=("promote", "--from", "preview", "--to", "dev"),
        ),
        VerboseCommandTestCase(
            description="rollback",
            expected_argv=("rollback", "--virtual-env", "dev"),
        ),
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
