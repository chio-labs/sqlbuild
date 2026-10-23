"""E2E coverage of description layout and quote repair by `sqb format`."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.format._test_types import (
    DescriptionLayoutTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_PROJECT_FILE: str = (
    'name = "shop"\nadapter = "duckdb"\n\n[connection]\ndatabase = "shop.duckdb"\n\n'
    "[scopes]\nenforce_placement = false\n"
)
_BODY: str = "\nSELECT 1 AS customer_id\n"


def _stored_descriptions(project_dir: Path) -> dict[str, str]:
    dag: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "dag", "--json")
    )
    assert dag.returncode == 0, dag.stderr
    return {node["name"]: node["description"] for node in json.loads(dag.stdout)["nodes"]}


@pytest.mark.parametrize(
    "test_case",
    [
        DescriptionLayoutTestCase(
            description="continuation_lines_at_column_zero_become_an_indented_block",
            header=(
                "MODEL (\n"
                "  description \"True when a name starts with a woman's title: Mme, Mlle, Miss, "
                "Mrs, Ms. Any case,\n"
                "with or without a dot ('MISS SARAH BOWEN', 'Mrs. C. O'Leary', 'Ms.Johnston').\",\n"
                ");\n"
            ),
            expected_header=(
                "MODEL (\n"
                '  description """\n'
                "    True when a name starts with a woman's title: Mme, Mlle, Miss, Mrs, Ms. Any "
                "case, with or\n"
                "    without a dot ('MISS SARAH BOWEN', 'Mrs. C. O'Leary', 'Ms.Johnston').\n"
                '  """,\n'
                ");\n"
            ),
        ),
        DescriptionLayoutTestCase(
            description="a_short_wrapped_description_is_joined",
            header='MODEL (\n  description "One row per\n    customer.",\n);\n',
            expected_header='MODEL (\n  description "One row per customer.",\n);\n',
        ),
        DescriptionLayoutTestCase(
            description="a_short_description_with_quotes_stays_one_triple_quoted_line",
            header='MODEL (\n  description """Matches "Miss" titles.""",\n);\n',
            expected_header='MODEL (\n  description """Matches "Miss" titles.""",\n);\n',
        ),
        DescriptionLayoutTestCase(
            description="a_long_description_with_quotes_becomes_a_block",
            header=(
                "MODEL (\n"
                '  description """True when a name starts with a title, with or without a dot '
                '("MISS SARAH BOWEN", "Mrs. C. O\'Leary", "Ms.Johnston").""",\n'
                ");\n"
            ),
            expected_header=(
                "MODEL (\n"
                '  description """\n'
                "    True when a name starts with a title, with or without a dot "
                '("MISS SARAH BOWEN", "Mrs. C.\n'
                '    O\'Leary", "Ms.Johnston").\n'
                '  """,\n'
                ");\n"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_description_when_formatting_then_layout_is_canonical_and_text_unchanged(
    test_case: DescriptionLayoutTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="shop",
        repo_files={
            "sqlbuild_project.toml": _PROJECT_FILE,
            "models/customers.sql": test_case.header + _BODY,
        },
    )
    before: dict[str, str] = _stored_descriptions(project_dir)

    formatted: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "format")
    )
    checked: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "format", "--check")
    )

    assert formatted.returncode == 0, formatted.stdout + formatted.stderr
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert ", 0 changed)" in checked.stderr
    model: str = (project_dir / "models/customers.sql").read_text()
    assert model == test_case.expected_header + _BODY
    assert _stored_descriptions(project_dir) == before


def test_given_descriptions_escaping_quotes_when_format_fix_then_triple_quoted_real_quotes(
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="shop",
        repo_files={
            "sqlbuild_project.toml": _PROJECT_FILE,
            "models/customers.sql": (
                'MODEL (\n  description "Matches a title (\\"Miss\\").",\n);\n'
                "\nSELECT @sql.title('Miss') AS title\n"
            ),
            "macros/sql/title.sql": (
                "MACRO (\n"
                "  description \"True when a name starts with a woman's title: Mme, Mlle, Miss, "
                "Mrs, Ms. Any case,\n"
                'with or without a dot (\\"MISS SARAH BOWEN\\", \\"Mrs. C. O\'Leary\\").",\n'
                "  arguments (value VARCHAR),\n  returns VARCHAR,\n);\n\n@value\n"
            ),
        },
    )
    failed: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "compile")
    )

    fixed: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "format", "--fix", "--json")
    )
    compiled: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "compile")
    )
    checked: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "format", "--check")
    )

    assert failed.returncode != 0
    payload: dict[str, Any] = json.loads(fixed.stdout)
    quote_fixes: list[dict[str, Any]] = [
        fix for fix in payload["rule_fixes"] if fix["code"] == "description-quotes"
    ]
    assert sorted((Path(fix["file"]).name, fix["line"], fix["status"]) for fix in quote_fixes) == [
        ("customers.sql", 2, "applied"),
        ("title.sql", 2, "applied"),
    ]
    assert any(violation["code"] == "format-fix-skipped" for violation in payload["violations"])
    assert (
        (project_dir / "models/customers.sql")
        .read_text()
        .startswith('MODEL (\n  description """Matches a title ("Miss").""",\n);\n')
    )
    assert (
        (project_dir / "macros/sql/title.sql")
        .read_text()
        .startswith(
            "MACRO (\n"
            '  description """\n'
            "    True when a name starts with a woman's title: Mme, Mlle, Miss, Mrs, Ms. Any case, "
            "with or\n"
            '    without a dot ("MISS SARAH BOWEN", "Mrs. C. O\'Leary").\n'
            '  """,\n'
        )
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert _stored_descriptions(project_dir)["customers"] == 'Matches a title ("Miss").'
