from __future__ import annotations

import pytest

from sqlbuild.cli.commands._helpers.debug.output import format_debug_json, format_debug_text
from sqlbuild.cli.commands.models import (
    DebugLine,
    DebugResult,
)
from sqlbuild.cli.commands.types import DebugCheckStatus
from tests.unit.src.sqlbuild.cli.commands._helpers.debug._test_types import (
    DebugOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DebugOutputTestCase(
            description="renders diagnostics sections and json sections",
            result=DebugResult(
                runtime=(DebugLine("sqlbuild version", "0.2.1"),),
                configuration=(
                    DebugLine(
                        "project file",
                        "/repo/sqlbuild_project.toml",
                        DebugCheckStatus.OK,
                        "found and valid",
                    ),
                ),
                providers=(
                    DebugLine("providers", "1", DebugCheckStatus.OK, "discovered"),
                    DebugLine(
                        "marker_provider",
                        "providers/marker.py:MarkerProvider",
                        DebugCheckStatus.OK,
                        "valid settings",
                    ),
                ),
                connection=(
                    DebugLine("token", "****"),
                    DebugLine(
                        "connection test", "", DebugCheckStatus.ERROR, "authentication failed"
                    ),
                    DebugLine("query test", "", DebugCheckStatus.SKIP, "connection failed"),
                ),
            ),
            expected_text=(
                "\n"
                "SQLBuild Diagnostics\n"
                "\n"
                "Runtime:\n"
                "  sqlbuild version: 0.2.1\n"
                "\n"
                "Configuration:\n"
                "  project file: /repo/sqlbuild_project.toml [OK found and valid]\n"
                "\n"
                "Providers:\n"
                "  providers: 1 [OK discovered]\n"
                "  marker_provider: providers/marker.py:MarkerProvider [OK valid settings]\n"
                "\n"
                "Connection:\n"
                "  token: ****\n"
                "  connection test: [ERROR authentication failed]\n"
                "  query test: [SKIP connection failed]\n"
                "\n"
            ),
            expected_json_fragment='"success": false',
            expected_color_fragments=(
                "\033[34m\033[1mSQLBuild Diagnostics\033[0m",
                "\033[1mRuntime:\033[0m",
                "\033[32m[OK found and valid]\033[0m",
                "\033[38;5;167m[ERROR authentication failed]\033[0m",
                "\033[2m[SKIP connection failed]\033[0m",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_debug_result_when_formatting_then_renders_expected_outputs(
    test_case: DebugOutputTestCase,
) -> None:
    text: str = format_debug_text(result=test_case.result, use_color=False)
    color_text: str = format_debug_text(result=test_case.result, use_color=True)
    json_text: str = format_debug_json(test_case.result)

    assert text == test_case.expected_text
    assert test_case.expected_json_fragment in json_text
    assert '"status": "ERROR"' in json_text
    assert '"status_message": "authentication failed"' in json_text
    for fragment in test_case.expected_color_fragments:
        assert fragment in color_text
