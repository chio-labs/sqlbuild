"""A Snowflake source whose columns are stored in quoted mixed case plans and builds offline."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.executor.build.snowflake_metadata._test_types import (
    QuotedColumnBuildTestCase,
)
from tests.integration.src.sqlbuild.executor.build.snowflake_metadata.helpers import (
    SimulatedSnowflakeWarehouse,
    build_with_cli,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    FakeColumn,
    FakeRelation,
)

_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "partner_feed"\nadapter = "snowflake"\n\n'
        '[connection]\naccount = "example"\nuser = "example"\n'
        'database = "analytics"\nschema = "marts"\n\n'
        '[defaults]\ndatabase = "analytics"\nschema = "marts"\nmaterialized = "table"\n'
    ),
    "sources/raw.yml": (
        "sources:\n"
        "  - name: raw_listings\n    description: Partner listings in quoted camelCase.\n"
        "    database: analytics\n    schema: raw\n    table: listings\n"
        "    columns:\n"
        "      - name: '\"listingId\"'\n        type: VARCHAR\n"
        "      - name: '\"unitPriceMinor\"'\n        type: NUMBER(38,0)\n"
    ),
    "models/stg_listings.sql": (
        "MODEL (description 'Listings renamed to snake case.');\n\n"
        'SELECT s."listingId" AS listing_id, s."unitPriceMinor" AS unit_price_minor\n'
        'FROM __source("raw_listings") AS s\n'
    ),
    "models/listing_export.sql": (
        "MODEL (\n  description 'Listings in the partner feed format.',\n"
        '  columns ("listingId" (nullable false, audits [not_null]),),\n);\n\n'
        'WITH final AS (\n  SELECT l.listing_id AS "listingId"\n'
        '  FROM __ref("stg_listings") AS l\n)\n\nSELECT *\nFROM final\n'
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        QuotedColumnBuildTestCase(
            description="quoted camelCase source columns bind in planning on a first build and rebuild",
            stored_columns=("listingId", "unitPriceMinor"),
            expected_fragment='"listingId" IS NULL',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_quoted_mixed_case_source_columns_when_building_then_planning_binds_them(
    test_case: QuotedColumnBuildTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for relative, content in _PROJECT_FILES.items():
        path: Path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(content, encoding="utf-8")
    columns: tuple[FakeColumn, ...] = tuple(
        FakeColumn(name=name, data_type="TEXT") for name in test_case.stored_columns
    )
    warehouse: SimulatedSnowflakeWarehouse = SimulatedSnowflakeWarehouse(
        relations=(
            FakeRelation(database="ANALYTICS", schema="RAW", name="LISTINGS", columns=columns),
        ),
    )

    builds: tuple[tuple[int, tuple[str, ...]], ...] = tuple(
        build_with_cli(project_dir=tmp_path, warehouse=warehouse, monkeypatch=monkeypatch)
        for _ in range(2)
    )

    output: str = capsys.readouterr().out
    assert tuple(build[0] for build in builds) == (0, 0), output
    assert "B002" not in output, output
    assert any(test_case.expected_fragment in statement for statement in builds[1][1]), builds[1][1]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
