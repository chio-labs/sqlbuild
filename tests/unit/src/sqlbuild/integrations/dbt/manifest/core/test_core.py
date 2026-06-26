from __future__ import annotations

import pytest

from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from tests.unit.src.sqlbuild.integrations.dbt.manifest.core._test_types import (
    DbtConfigStripTestCase,
)

TEST_CASES: list[DbtConfigStripTestCase] = [
    DbtConfigStripTestCase(
        description="strips multi-line config block with nested meta dict braces",
        raw_code=(
            "{{ config(\n"
            "    materialized='table',\n"
            "    unique_key='order_id',\n"
            "    meta={'sqlbuild': {'cursor': 'updated_at', 'cursor_type': 'timestamp'}}\n"
            ") }}\n\n"
            "select 1 as order_id, 900 as amount_cents, "
            "cast('2026-06-17 00:00:00' as timestamp) as updated_at\n"
        ),
        expected_body_line=(
            "select 1 as order_id, 900 as amount_cents, "
            "cast('2026-06-17 00:00:00' as timestamp) as updated_at"
        ),
        expected_absent_fragment=") }}",
    ),
    DbtConfigStripTestCase(
        description="strips simple single-key config block",
        raw_code="{{ config(materialized='table') }}\nselect 1 as id\n",
        expected_body_line="select 1 as id",
        expected_absent_fragment="config",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_config_block_when_building_manifest_then_definition_fingerprint_excludes_config(
    test_case: DbtConfigStripTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data={
            "nodes": {
                "model.analytics.orders": {
                    "resource_type": "model",
                    "name": "orders",
                    "package_name": "analytics",
                    "database": "warehouse",
                    "schema": "main",
                    "alias": "orders",
                    "raw_code": test_case.raw_code,
                }
            }
        }
    )

    model: DbtManifestModel = manifest.models_by_unique_id["model.analytics.orders"]
    body_line: str = model.definition_fingerprint.splitlines()[0]

    assert body_line == test_case.expected_body_line
    assert test_case.expected_absent_fragment not in model.definition_fingerprint
