"""E2E coverage for sqb test progress rows in a real terminal."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import (
    TerminalTestProgressE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    SPINNER_GLYPHS,
    assert_fragments_in_order,
    prepare_waffle_shop,
    render_terminal_screen,
    run_sqb,
    run_sqb_with_pty,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TerminalTestProgressE2ETestCase(
            description="test rows replace their spinner and statement narration stays separate",
            columns=100,
            expected_screen_fragments=(
                "✓ Warehouse connected  duckdb",
                "test      test_stg_orders",
                "PASS=<n>  FAIL=<n>  TOTAL=<n>",
            ),
            expected_summary="PASS=5  FAIL=0  TOTAL=5",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_built_project_when_testing_in_terminal_then_no_spinner_row_survives(
    tmp_path: Path, test_case: TerminalTestProgressE2ETestCase
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    built: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    result: subprocess.CompletedProcess[str] = run_sqb_with_pty(
        command=("test",), project_dir=project_dir, columns=test_case.columns, timeout_seconds=180.0
    )
    screen: tuple[str, ...] = render_terminal_screen(
        output=result.stdout, columns=test_case.columns
    )
    rendered: str = "\n".join(screen)

    assert built.returncode == 0, built.stdout + built.stderr
    assert result.returncode == 0, rendered
    assert not any(glyph in rendered for glyph in SPINNER_GLYPHS), rendered
    assert not any(line.lstrip().startswith("test ") and "statement" in line for line in screen), (
        rendered
    )
    assert_fragments_in_order(rendered, test_case.expected_screen_fragments)
    assert test_case.expected_summary in rendered


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
