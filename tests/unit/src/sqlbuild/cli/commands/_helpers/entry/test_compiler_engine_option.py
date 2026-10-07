"""The hidden --compiler-engine flag overrides SQLBUILD_COMPILER_ENGINE and both are validated."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands._helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.entry.models import ParsedCliInvocation
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from tests.unit.src.sqlbuild.cli.commands._helpers.entry._test_types import (
    CompilerEngineOptionTestCase,
    HiddenOptionTestCase,
    RejectedCompilerEngineTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompilerEngineOptionTestCase(
            description="default_leaves_engine_to_environment",
            argv=("compile",),
            environment_value="",
            expected_engine=None,
        ),
        CompilerEngineOptionTestCase(
            description="flag_before_subcommand",
            argv=("--compiler-engine", "native", "compile"),
            environment_value="",
            expected_engine="native",
        ),
        CompilerEngineOptionTestCase(
            description="preview_flag",
            argv=("--compiler-engine", "native-preview", "compile"),
            environment_value="",
            expected_engine="native-preview",
        ),
        CompilerEngineOptionTestCase(
            description="flag_after_subcommand",
            argv=("plan", "--compiler-engine", "python"),
            environment_value="",
            expected_engine="python",
        ),
        CompilerEngineOptionTestCase(
            description="flag_overrides_invalid_environment",
            argv=("compile", "--compiler-engine", "python"),
            environment_value="rust",
            expected_engine="python",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_selection_when_parsing_then_flag_value_is_recorded(
    test_case: CompilerEngineOptionTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.environment_value)

    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.args is not None
    assert parsed.args.compiler_engine == test_case.expected_engine


@pytest.mark.parametrize(
    "test_case",
    [
        RejectedCompilerEngineTestCase(
            description="unknown_flag_value",
            argv=("compile", "--compiler-engine", "rust"),
            environment_value="",
            expected_exit_code=2,
            expected_error="argument --compiler-engine: invalid choice: 'rust'",
        ),
        RejectedCompilerEngineTestCase(
            description="unknown_environment_value",
            argv=("compile",),
            environment_value="rust",
            expected_exit_code=2,
            expected_error=(
                "SQLBUILD_COMPILER_ENGINE must be one of python, native, native-preview "
                "(got 'rust')"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_engine_when_parsing_then_usage_error_names_accepted_values(
    test_case: RejectedCompilerEngineTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.environment_value)

    parsed: ParsedCliInvocation = parse_cli_invocation(
        argv=test_case.argv, parser=build_cli_parser()
    )

    assert parsed.args is None
    assert parsed.exit_code == test_case.expected_exit_code
    assert test_case.expected_error in capsys.readouterr().err


@pytest.mark.parametrize(
    "test_case",
    [
        HiddenOptionTestCase(
            description="root_help", option="--compiler-engine", expected_listed=False
        )
    ],
    ids=lambda case: case.description,
)
def test_given_root_help_when_rendering_then_compiler_engine_flag_stays_hidden(
    test_case: HiddenOptionTestCase,
) -> None:
    assert (test_case.option in build_cli_parser().format_help()) is test_case.expected_listed


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
