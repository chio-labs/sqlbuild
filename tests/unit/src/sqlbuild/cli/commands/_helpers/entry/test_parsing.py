"""Tests for cross-command CLI output mode normalization."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands._helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.commands.models import ParsedCliInvocation
from tests.unit.src.sqlbuild.cli.commands._helpers.entry._test_types import (
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
