"""Integration coverage for authored-source native lint diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.cells import cell_len

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    LintDiagnosticIntegrationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LintDiagnosticIntegrationTestCase(
            description="unordered limit diagnostic",
            model_name="limited",
            source_line="SELECT id FROM items LIMIT 1",
            expected_code="SQBL004",
            expected_message="Row selection is nondeterministic",
            expected_location="models/limited.sql:2:22",
            expected_caret_suffix="^^^^^",
            expected_remediation=(
                "Add ORDER BY with a deterministic tie-breaker before LIMIT or OFFSET."
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unhealthy_sql_when_running_real_cli_then_diagnostic_is_actionable(
    test_case: LintDiagnosticIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exercise discovery, expansion, native lint, source mapping, and terminal rendering."""

    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "demo"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / f"{test_case.model_name}.sql"
    model.parent.mkdir()
    _ = model.write_text(
        f'MODEL (description "Demonstrate lint diagnostics");\n{test_case.source_line}\n',
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--no-color",
            "--project-dir",
            str(tmp_path),
            "lint",
            "--select",
            test_case.model_name,
        ]
    )

    assert exit_code == 1
    output: str = capsys.readouterr().out
    assert f"warning[{test_case.expected_code}]: {test_case.expected_message}" in output
    assert f" --> {test_case.expected_location}" in output
    assert f"2 | {test_case.source_line}" in output
    assert test_case.expected_caret_suffix in output
    assert f"  = help: {test_case.expected_remediation}" in output
    assert "native" not in output
    assert "\033[" not in output


@pytest.mark.parametrize(
    "test_case",
    [
        LintDiagnosticIntegrationTestCase(
            description="tab and wide Unicode before unordered limit",
            model_name="unicode",
            source_line="SELECT\t'界' AS label FROM items LIMIT 1",
            expected_code="SQBL004",
            expected_message="Row selection is nondeterministic",
            expected_location="models/unicode.sql:2:32",
            expected_caret_suffix="^^^^^",
            expected_remediation=(
                "Add ORDER BY with a deterministic tie-breaker before LIMIT or OFFSET."
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_tabs_and_unicode_before_finding_when_rendering_then_caret_visually_aligns(
    test_case: LintDiagnosticIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "demo"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / f"{test_case.model_name}.sql"
    model.parent.mkdir()
    _ = model.write_text(
        f'MODEL (description "Demonstrate display alignment");\n{test_case.source_line}\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "lint"])

    assert exit_code == 1
    output_lines: list[str] = capsys.readouterr().out.splitlines()
    rendered_source: str = f"2 | {test_case.source_line}"
    source_index: int = output_lines.index(rendered_source)
    rendered_caret: str = output_lines[source_index + 1]
    source_prefix: str = rendered_source.removeprefix("2 | ").split("LIMIT", maxsplit=1)[0]
    caret_padding: str = rendered_caret.removeprefix("  | ").split("^", maxsplit=1)[0]
    assert cell_len(source_prefix.expandtabs()) == cell_len(caret_padding.expandtabs())
    assert rendered_caret.endswith(test_case.expected_caret_suffix)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
