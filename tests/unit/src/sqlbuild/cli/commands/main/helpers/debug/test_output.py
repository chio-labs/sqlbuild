from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.debug.models import (
    DebugLine,
    DebugResult,
)
from sqlbuild.cli.commands.main.helpers.debug.output import format_debug_json, format_debug_text
from sqlbuild.cli.commands.main.helpers.debug.types import DebugCheckStatus
from tests.unit.src.sqlbuild.cli.commands.main.helpers.debug._test_types import (
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
                "Connection:\n"
                "  token: ****\n"
                "  connection test: [ERROR authentication failed]\n"
                "  query test: [SKIP connection failed]\n"
                "\n"
            ),
            expected_json_fragment='"success": false',
        )
    ],
    ids=["renders aligned text and json checks"],
)
def test_given_debug_result_when_formatting_then_renders_expected_outputs(
    test_case: DebugOutputTestCase,
) -> None:
    text: str = format_debug_text(test_case.result, use_color=False)
    json_text: str = format_debug_json(test_case.result)

    assert text == test_case.expected_text
    assert test_case.expected_json_fragment in json_text
    assert '"status": "ERROR"' in json_text
    assert '"status_message": "authentication failed"' in json_text
