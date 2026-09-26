"""Real compiler regressions for binding boundary review findings."""

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import NativeCatalogCase


@pytest.mark.parametrize(
    "test_case",
    [
        NativeCatalogCase(
            "open USING",
            'SELECT * FROM __source("orders") o JOIN __source("customers") c USING (id)',
        ),
        NativeCatalogCase(
            "open QUALIFY",
            'SELECT o.id, ROW_NUMBER() OVER () AS n FROM __source("orders") o QUALIFY o.quantity > 1',
        ),
        NativeCatalogCase(
            "closed QUALIFY",
            'SELECT o.id, ROW_NUMBER() OVER () AS n FROM __source("known") o QUALIFY o.quantity > 1',
            ("B002",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_open_sources_when_validating_clauses_then_only_closed_shapes_prove_missing_columns(
    test_case: NativeCatalogCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources/orders.yml").write_text(
        "sources:\n  - name: orders\n    table: orders\n  - name: customers\n    table: customers\n"
        "  - name: known\n    table: known\n    contract: enforced\n    columns:\n      - name: id\n        type: INTEGER\n"
    )
    (tmp_path / "models").mkdir()
    (tmp_path / "models/report.sql").write_text("MODEL (materialized view);\n" + test_case.sql)
    result: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache", "--json"])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["code"] for item in payload["diagnostics"]) == test_case.expected_codes
    assert result == int(bool(test_case.expected_codes))


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
