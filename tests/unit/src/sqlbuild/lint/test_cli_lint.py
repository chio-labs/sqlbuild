"""Unit tests for the sqb lint and sqb format commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.cli.commands.main.project import _lint
from tests.unit.src.sqlbuild.lint._test_types import (
    FixCliTestCase,
    FormatCliTestCase,
    LintBehaviorTestCase,
    LintCliTestCase,
)

CLEAN_MODEL: str = 'MODEL (\n  materialized table,\n  description "ok"\n);\nSELECT 1 AS x FROM t\n'
COMMENTED_MODEL: str = "-- A comment.\nMODEL (\n  materialized table\n);\nSELECT 1 AS x FROM t\n"
NO_DESCRIPTION_MODEL: str = "MODEL (\n  materialized table\n);\nSELECT 1 AS x FROM t\n"
PROJECT_TOML: str = 'name = "demo"\nadapter = "duckdb"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        LintCliTestCase(
            description="lint reports violations and exits nonzero",
            files={"models/no_description.sql": NO_DESCRIPTION_MODEL},
            expected_exit_code=1,
            expected_output_fragments=("description-present", "FAULT=1"),
        ),
        LintCliTestCase(
            description="lint on a clean project exits zero",
            files={"models/fine.sql": CLEAN_MODEL},
            expected_exit_code=0,
        ),
        LintCliTestCase(
            description="lint reports native semantic SQL diagnostics",
            files={
                "models/null_comparison.sql": (
                    'MODEL (description "ok");\nSELECT value FROM items WHERE value = NULL\n'
                ),
                "sqlbuild_project.toml": PROJECT_TOML,
            },
            expected_exit_code=1,
            expected_output_fragments=(
                "warning[SQBL001]: Comparison with NULL is never true",
                " --> models/null_comparison.sql:2:37",
                "2 | SELECT value FROM items WHERE value = NULL",
                "  |                                     ^",
                "  = help: Use IS NULL or IS NOT NULL when testing for NULL.",
                "WARN=1",
            ),
        ),
        LintCliTestCase(
            description="lint uses the local adapter override dialect",
            files={
                "models/clean.sql": CLEAN_MODEL,
                "sqlbuild_project.toml": 'name = "demo"\nadapter = "unsupported"\n',
                "sqlbuild_local.toml": 'adapter = "duckdb"\n',
            },
            expected_exit_code=0,
        ),
        LintCliTestCase(
            description="lint rule prefixes and ignores select optional catalogue entries",
            files={
                "models/limited.sql": ('MODEL (description "ok");\nSELECT id FROM items LIMIT 1\n'),
                "sqlbuild_project.toml": (
                    'name = "demo"\nadapter = "duckdb"\n'
                    '[lint]\nselect = ["SQBL"]\nignore = ["SQBL004"]\n'
                ),
            },
            expected_exit_code=0,
            expected_output_fragments=("WARN=0",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_running_lint_then_exit_code_and_output_match_expected(
    test_case: LintCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    file_relative_path: str
    file_contents: str
    for file_relative_path, file_contents in test_case.files.items():
        write_target: Path = tmp_path / file_relative_path
        _ = write_target.parent.mkdir(parents=True, exist_ok=True)
        _ = write_target.write_text(file_contents, encoding="utf-8")
    arguments: list[str] = [
        "--project-dir",
        str(tmp_path),
        "lint",
        *test_case.extra_arguments,
    ]
    exit_code: int = main(arguments)
    assert exit_code == test_case.expected_exit_code
    output: str = capsys.readouterr().out
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    relative_path: str
    file_fragment: str
    for relative_path, file_fragment in test_case.expected_file_fragments.items():
        written: str = (tmp_path / relative_path).read_text(encoding="utf-8")
        assert file_fragment in written


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCliTestCase(
            description="format relocates leading comments in place",
            files={"models/commented.sql": COMMENTED_MODEL},
            expected_exit_code=0,
            expected_output_fragments=("Formatted files:",),
            expected_file_fragments={"models/commented.sql": 'description "A comment.",'},
        ),
        FormatCliTestCase(
            description="format exits nonzero when faults remain",
            files={"models/no_description.sql": NO_DESCRIPTION_MODEL},
            expected_exit_code=1,
            expected_output_fragments=("FAULT=1",),
        ),
        FormatCliTestCase(
            description="format exits nonzero when native semantic warnings remain",
            files={
                "sqlbuild_project.toml": (
                    'name = "demo"\nadapter = "duckdb"\n[vars]\ncolumns = "a,b"\n'
                ),
                "models/generated.sql": (
                    'MODEL (\n  description "ok"\n);\nSELECT @@columns FROM t LIMIT 1\n'
                ),
            },
            expected_exit_code=1,
            expected_output_fragments=("WARN=1", "SQBL004"),
            extra_arguments=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_running_format_then_results_match_expected(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    file_relative_path: str
    file_contents: str
    for file_relative_path, file_contents in test_case.files.items():
        write_target: Path = tmp_path / file_relative_path
        _ = write_target.parent.mkdir(parents=True, exist_ok=True)
        _ = write_target.write_text(file_contents, encoding="utf-8")
    exit_code: int = main(["--project-dir", str(tmp_path), "format", *test_case.extra_arguments])
    assert exit_code == test_case.expected_exit_code
    output: str = capsys.readouterr().out
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    relative_path: str
    file_fragment: str
    for relative_path, file_fragment in test_case.expected_file_fragments.items():
        written: str = (tmp_path / relative_path).read_text(encoding="utf-8")
        assert file_fragment in written


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="one selected model", expected_value="first.sql")],
    ids=lambda case: case.description,
)
def test_given_model_selector_when_linting_then_only_selected_file_is_checked(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    models: Path = tmp_path / "models"
    models.mkdir()
    for name in ("first", "second"):
        _ = (models / f"{name}.sql").write_text(
            f'MODEL (name {name}, description "ok");\nSELECT value FROM items WHERE value = NULL\n',
            encoding="utf-8",
        )

    exit_code: int = main(["--project-dir", str(tmp_path), "lint", "--select", "first"])

    assert exit_code == 1
    output: str = capsys.readouterr().out
    assert str(test_case.expected_value) in output
    assert "second.sql" not in output
    assert "FILES=1" in output


@pytest.mark.parametrize(
    "test_case",
    [
        LintBehaviorTestCase(
            description="zero matching tag selector",
            expected_value="no models found with tag 'missing'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_zero_match_selector_when_linting_then_command_fails_closed(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "first.sql"
    model.parent.mkdir()
    _ = model.write_text(
        'MODEL (name first, description "ok");\nSELECT 1 AS value\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "lint", "--select", "tag:missing"])

    assert exit_code == 1
    captured: CaptureResult[str] = capsys.readouterr()
    assert str(test_case.expected_value) in captured.err


@pytest.mark.parametrize(
    "test_case",
    [
        LintBehaviorTestCase(
            description="selector file narrowed by exclusion", expected_value="first.sql"
        )
    ],
    ids=lambda case: case.description,
)
def test_given_select_file_and_exclude_when_linting_then_canonical_scope_is_applied(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    models: Path = tmp_path / "models"
    models.mkdir()
    for name in ("first", "second"):
        _ = (models / f"{name}.sql").write_text(
            f'MODEL (name {name}, description "ok");\nSELECT value FROM items WHERE value = NULL\n',
            encoding="utf-8",
        )
    selectors: Path = tmp_path / "selectors.txt"
    _ = selectors.write_text("first\nsecond\n", encoding="utf-8")

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "lint",
            "--select-file",
            str(selectors),
            "--exclude",
            "second",
        ]
    )

    assert exit_code == 1
    output: str = capsys.readouterr().out
    assert str(test_case.expected_value) in output
    assert "second.sql" not in output
    assert "FILES=1" in output


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="format check dry run", expected_value=1)],
    ids=lambda case: case.description,
)
def test_given_unformatted_sql_when_format_checking_then_fails_without_writing(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    original: str = 'MODEL (description "ok");\nselect a,b from items\n'
    model: Path = tmp_path / "models" / "messy.sql"
    model.parent.mkdir()
    _ = model.write_text(original, encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "format", "--check"])

    assert exit_code == test_case.expected_value
    assert model.read_text(encoding="utf-8") == original
    assert "Would format files:" in capsys.readouterr().out


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="format unified diff dry run", expected_value=0)],
    ids=lambda case: case.description,
)
def test_given_unformatted_sql_when_diffing_then_prints_diff_without_writing(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    original: str = 'MODEL (description "ok");\nselect a,b from items\n'
    model: Path = tmp_path / "models" / "messy.sql"
    model.parent.mkdir()
    _ = model.write_text(original, encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "format", "--diff"])

    assert exit_code == test_case.expected_value
    assert model.read_text(encoding="utf-8") == original
    output: str = capsys.readouterr().out
    assert f"--- {model}" in output
    assert "-select a,b from items" in output
    assert "+SELECT" in output


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="native warning JSON output", expected_value=1)],
    ids=lambda case: case.description,
)
def test_given_native_warning_when_linting_as_json_then_emits_machine_readable_result(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "warning.sql"
    model.parent.mkdir()
    _ = model.write_text(
        'MODEL (description "ok");\nSELECT value FROM items WHERE value = NULL\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "lint", "--json"])

    assert exit_code == 1
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert payload["files_checked"] == 1
    assert payload["warnings"] == test_case.expected_value
    assert isinstance(payload["violations"], list)
    violation: dict[str, object] = payload["violations"][0]
    assert violation["code"] == "SQBL001"
    assert violation["message"] == "Comparison with NULL is never true"
    assert violation["remediation"] == "Use IS NULL or IS NOT NULL when testing for NULL."
    assert (violation["line"], violation["column"]) == (2, 37)
    assert (violation["end_line"], violation["end_column"]) == (2, 38)


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="color-capable terminal", expected_value=1)],
    ids=lambda case: case.description,
)
def test_given_color_terminal_when_linting_then_severity_and_caret_are_styled(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "warning.sql"
    model.parent.mkdir()
    _ = model.write_text(
        'MODEL (description "ok");\nSELECT value FROM items WHERE value = NULL\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(_lint, "supports_color", lambda: True)

    exit_code: int = _lint.run_lint_command(project_dir=tmp_path)

    assert exit_code == test_case.expected_value
    output: str = capsys.readouterr().out
    assert "\033[33m\033[1mwarning[SQBL001]\033[0m" in output
    assert "\033[33m\033[1m^\033[0m" in output
    assert "\033[2m= help:\033[0m" in output


@pytest.mark.parametrize(
    "test_case",
    [
        FixCliTestCase(
            description="write mode applies proven semantic repairs",
            original_sql=(
                'MODEL (description "fix");\n'
                "WITH unused AS (SELECT 9 AS id)\n"
                "SELECT DISTINCT value FROM items JOIN other WHERE value = NULL GROUP BY value\n"
            ),
            arguments=(),
            expected_exit_code=0,
            expected_sql=(
                'MODEL (description "fix");\n'
                "SELECT value FROM items CROSS JOIN other WHERE value IS NULL GROUP BY value\n"
            ),
            expected_output_fragments=(
                "fixed[SQBL001]",
                "fixed[SQBL003]",
                "fixed[SQBL005]",
                "fixed[SQBL006]",
                "FIXED=4",
                "REMAINING=0",
            ),
        ),
        FixCliTestCase(
            description="check mode previews without writing",
            original_sql=(
                'MODEL (description "fix");\nSELECT value FROM items WHERE value = NULL\n'
            ),
            arguments=("--check",),
            expected_exit_code=1,
            expected_sql=(
                'MODEL (description "fix");\nSELECT value FROM items WHERE value = NULL\n'
            ),
            expected_output_fragments=("fixed[SQBL001]", "WOULD_FIX=1"),
        ),
        FixCliTestCase(
            description="diff mode shows edits without writing",
            original_sql=(
                'MODEL (description "fix");\nSELECT value FROM items WHERE value <> NULL\n'
            ),
            arguments=("--diff",),
            expected_exit_code=1,
            expected_sql=(
                'MODEL (description "fix");\nSELECT value FROM items WHERE value <> NULL\n'
            ),
            expected_output_fragments=(
                "-SELECT value FROM items WHERE value <> NULL",
                "+SELECT value FROM items WHERE value IS NOT NULL",
                "WOULD_FIX=1",
            ),
        ),
        FixCliTestCase(
            description="unfixable finding remains actionable",
            original_sql=('MODEL (description "fix");\nSELECT id FROM items LIMIT 1\n'),
            arguments=(),
            expected_exit_code=1,
            expected_sql=('MODEL (description "fix");\nSELECT id FROM items LIMIT 1\n'),
            expected_output_fragments=(
                "skipped[SQBL004]",
                "deterministic ordering columns",
                "REMAINING=1",
            ),
        ),
        FixCliTestCase(
            description="optional selected rule participates in fix",
            original_sql=(
                'MODEL (description "fix");\n'
                "SELECT 'é' AS label, CASE WHEN active THEN TRUE ELSE FALSE END AS active FROM items\n"
            ),
            arguments=(),
            expected_exit_code=0,
            expected_sql=(
                'MODEL (description "fix");\n'
                "SELECT 'é' AS label, COALESCE(active, FALSE) AS active FROM items\n"
            ),
            expected_output_fragments=("fixed[SQBL030]", "FIXED=1"),
            project_toml=('name = "demo"\nadapter = "duckdb"\n[lint]\nselect = ["SQBL030"]\n'),
        ),
        FixCliTestCase(
            description="stale suppression directive is removed",
            original_sql=(
                'MODEL (description "fix");\n'
                "-- sqb: ignore SQBL004 because this used to be limited\n"
                "SELECT id FROM items ORDER BY id\n"
            ),
            arguments=(),
            expected_exit_code=0,
            expected_sql=('MODEL (description "fix");\nSELECT id FROM items ORDER BY id\n'),
            expected_output_fragments=("fixed[SQBL000]", "FIXED=1"),
        ),
        FixCliTestCase(
            description="unicode before a native edit preserves authored offsets",
            original_sql=(
                "MODEL (description \"fix\");\nSELECT 'é' AS label FROM items WHERE value = NULL\n"
            ),
            arguments=(),
            expected_exit_code=0,
            expected_sql=(
                "MODEL (description \"fix\");\nSELECT 'é' AS label FROM items WHERE value IS NULL\n"
            ),
            expected_output_fragments=("fixed[SQBL001]", "FIXED=1"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_lint_findings_when_fixing_then_mode_contract_is_respected(
    test_case: FixCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        test_case.project_toml or PROJECT_TOML,
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "fix.sql"
    model.parent.mkdir()
    _ = model.write_text(test_case.original_sql, encoding="utf-8")

    exit_code: int = main(
        ["--no-color", "--project-dir", str(tmp_path), "fix", *test_case.arguments]
    )

    assert exit_code == test_case.expected_exit_code
    assert model.read_text(encoding="utf-8") == test_case.expected_sql
    output: str = capsys.readouterr().out
    for fragment in test_case.expected_output_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="fix JSON output", expected_value=1)],
    ids=lambda case: case.description,
)
def test_given_fixable_finding_when_checking_as_json_then_output_is_structured(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "fix.sql"
    model.parent.mkdir()
    original: str = 'MODEL (description "fix");\nSELECT value FROM items WHERE value = NULL\n'
    _ = model.write_text(original, encoding="utf-8")

    exit_code: int = main(
        ["--no-color", "--project-dir", str(tmp_path), "fix", "--check", "--json"]
    )

    assert exit_code == test_case.expected_value
    assert model.read_text(encoding="utf-8") == original
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "check"
    fixes: object = payload["fixes"]
    assert isinstance(fixes, list)
    assert fixes[0]["code"] == "SQBL001"
    assert fixes[0]["status"] == "fixed"
    assert payload["remaining"] == []
