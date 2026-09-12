from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.lineage.cache import relation_lineage_fingerprint
from tests.unit.src.sqlbuild.cli.commands._helpers.lineage._test_types import (
    LineageFingerprintAvailabilityTestCase,
    LineageFingerprintEnvironmentTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        LineageFingerprintEnvironmentTestCase(
            description="referenced environment value participates in cache identity",
            config=(
                'name = "orders"\nadapter = "duckdb"\n'
                '[targets.dev]\nschema = "${if(eq( ENV:ORDERS_SCHEMA, '
                "'orders_dev'), 'dev', 'test')}\"\n"
            ),
            environment_name="ORDERS_SCHEMA",
            first_value="orders_dev",
            second_value="orders_test",
            expected_equal=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_referenced_environment_change_when_fingerprinting_then_invalidates_cache_identity(
    test_case: LineageFingerprintEnvironmentTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.config, encoding="utf-8")
    monkeypatch.setenv(test_case.environment_name, test_case.first_value)
    first: str | None = relation_lineage_fingerprint(project_dir=tmp_path, cli_vars=None)
    monkeypatch.setenv(test_case.environment_name, test_case.second_value)

    second: str | None = relation_lineage_fingerprint(project_dir=tmp_path, cli_vars=None)

    assert (first == second) is test_case.expected_equal


@pytest.mark.parametrize(
    "test_case",
    (
        LineageFingerprintAvailabilityTestCase(
            description="dynamic invocation context disables structural cache",
            relative_path="sqlbuild_project.toml",
            config=(
                'name = "orders"\nadapter = "duckdb"\n'
                '[targets.dev]\nschema = "orders_${CTX:run_id}"\n'
            ),
            expected_available=False,
        ),
        LineageFingerprintAvailabilityTestCase(
            description="unicode environment name disables structural cache",
            relative_path="sqlbuild_project.toml",
            config=(
                'name = "orders"\nadapter = "duckdb"\n[targets.dev]\nschema = "${ENV:ORDERS_ÉTÉ}"\n'
            ),
            expected_available=False,
        ),
        LineageFingerprintAvailabilityTestCase(
            description="SQL output context preserves structural cache availability",
            relative_path="models/orders.sql",
            config=(
                "MODEL (materialized view);\n\n"
                "SELECT '${CTX:run_id}' AS invocation_id, 1 AS order_id\n"
            ),
            expected_available=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dynamic_invocation_context_when_fingerprinting_then_disables_cache(
    test_case: LineageFingerprintAvailabilityTestCase,
    tmp_path: Path,
) -> None:
    authored_path: Path = tmp_path / test_case.relative_path
    authored_path.parent.mkdir(parents=True, exist_ok=True)
    authored_path.write_text(test_case.config, encoding="utf-8")

    observed: str | None = relation_lineage_fingerprint(project_dir=tmp_path, cli_vars=None)

    assert (observed is not None) is test_case.expected_available
