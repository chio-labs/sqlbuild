"""Tests for rejecting unsupported keys in statement headers and model config layers."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.yml.project import load_project_config
from sqlbuild.compiler.discovery.exceptions import DiscoveryError, ProjectConfigError
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    StatementHeaderKeysTestCase,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers.helpers import parse_statement_header_file


@pytest.mark.parametrize(
    "test_case",
    [
        StatementHeaderKeysTestCase(
            description="MODEL typo is located and gets the nearest key",
            file_name="MODEL",
            contents=(
                "MODEL (\n  materialized table,\n  uniqe_key order_id,\n);\n\nSELECT 1 AS order_id\n"
            ),
            expected_error="MODEL() in 'orders.sql:3' has unsupported keys: uniqe_key",
            expected_help="did you mean 'unique_key'?",
        ),
        StatementHeaderKeysTestCase(
            description="MODEL comments are skipped and the typo line is still reported",
            file_name="MODEL",
            contents=(
                "MODEL (\n  -- owner: fulfillment team\n  materialized table,\n"
                "  /* keep the key, it's stable */\n  uniqe_key order_id,\n);\n\n"
                "SELECT 1 AS order_id\n"
            ),
            expected_error="MODEL() in 'orders.sql:5' has unsupported keys: uniqe_key",
            expected_help="did you mean 'unique_key'?",
        ),
        StatementHeaderKeysTestCase(
            description="MODEL legacy singular hook suggests the typed list key",
            file_name="MODEL",
            contents="MODEL (pre_hook 'SELECT 1');\n\nSELECT 1 AS order_id\n",
            expected_error="MODEL() in 'orders.sql:1' has unsupported keys: pre_hook",
            expected_help="did you mean 'pre_hooks'?",
        ),
        StatementHeaderKeysTestCase(
            description="MODEL removed cursor input key names the replacement",
            file_name="MODEL",
            contents=(
                "MODEL (\n  materialized incremental,\n  cursor_filter_inputs [stg_orders],\n);\n\n"
                "SELECT 1 AS order_id\n"
            ),
            expected_error="MODEL() in 'orders.sql:3' has unsupported keys: cursor_filter_inputs",
            expected_help="did you mean 'cursor_inputs'?",
        ),
        StatementHeaderKeysTestCase(
            description="MODEL unrelated keys list every key without a suggestion",
            file_name="MODEL",
            contents="MODEL (materialized table, zzz 1, qqq 2);\n\nSELECT 1 AS order_id\n",
            expected_error="MODEL() in 'orders.sql:1' has unsupported keys: zzz, qqq",
            expected_help="remove the key; see the reference for supported keys",
        ),
        StatementHeaderKeysTestCase(
            description="second AUDIT block reports its own file line",
            file_name="AUDIT",
            contents=(
                "AUDIT (name first_check);\nSELECT 1 WHERE FALSE;\n\n"
                "AUDIT (\n  name second_check,\n  severty warn,\n);\nSELECT 1 WHERE FALSE;\n"
            ),
            expected_error="AUDIT() in 'orders.sql:6' has unsupported keys: severty",
            expected_help="did you mean 'severity'?",
        ),
        StatementHeaderKeysTestCase(
            description="second TEST block reports its own file line",
            file_name="TEST",
            contents=(
                "TEST (name first_case);\nSELECT 1;\n\nTEST (\n  name second_case,\n"
                "  mdoe model,\n);\nSELECT 1;\n"
            ),
            expected_error="TEST() in 'orders.sql:6' has unsupported keys: mdoe",
            expected_help="did you mean 'mode'?",
        ),
        StatementHeaderKeysTestCase(
            description="HOOK lists its small supported key set",
            file_name="HOOK",
            contents="\nHOOK (owner orders_team);\nSELECT 1\n",
            expected_error="HOOK() in 'orders.sql:2' has unsupported keys: owner",
            expected_help="supported keys: description",
        ),
        StatementHeaderKeysTestCase(
            description="SCENARIO reports line and nearest key",
            file_name="SCENARIO",
            contents='SCENARIO (\n  descrption "Refund flow",\n);\nSELECT 1\n',
            expected_error="SCENARIO() in 'orders.sql:2' has unsupported keys: descrption",
            expected_help="did you mean 'description'?",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_header_key_when_parsing_then_rejects_with_location_and_help(
    test_case: StatementHeaderKeysTestCase,
) -> None:
    with pytest.raises(DiscoveryError) as raised:
        parse_statement_header_file(
            statement=test_case.file_name, contents=test_case.contents, file_path=Path("orders.sql")
        )

    assert raised.value.message == test_case.expected_error
    assert raised.value.help == test_case.expected_help


@pytest.mark.parametrize(
    "test_case",
    [
        StatementHeaderKeysTestCase(
            description="removed virtual environment option keeps its migration message",
            file_name="MODEL",
            contents="MODEL (materialized table, run_despite_unchanged always);\nSELECT 1 AS id\n",
            expected_error=(
                "MODEL() option(s) run_despite_unchanged in 'orders.sql' were removed with "
                "virtual environments; projects run in direct mode"
            ),
            expected_help="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_removed_model_key_when_parsing_then_explains_removal(
    test_case: StatementHeaderKeysTestCase,
) -> None:
    with pytest.raises(DiscoveryError) as raised:
        parse_statement_header_file(
            statement=test_case.file_name, contents=test_case.contents, file_path=Path("orders.sql")
        )

    assert raised.value.message == test_case.expected_error
    assert raised.value.code == "D002"


@pytest.mark.parametrize(
    "test_case",
    [
        StatementHeaderKeysTestCase(
            description="path default typo",
            file_name="sqlbuild_project.toml",
            contents=(
                'name = "orders"\nadapter = "duckdb"\n\n[path_defaults.staging]\n'
                'materialised = "view"\n'
            ),
            expected_error="path_defaults['staging'] contains unknown key(s): materialised.",
            expected_help="did you mean 'materialized'?",
        ),
        StatementHeaderKeysTestCase(
            description="project default that is not layered from TOML",
            file_name="sqlbuild_project.toml",
            contents='name = "orders"\nadapter = "duckdb"\n\n[defaults]\ntag = ["orders"]\n',
            expected_error="[defaults] contains unknown key(s): tag.",
            expected_help="did you mean 'tags'?",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_model_config_layer_key_when_loading_project_then_rejects_with_help(
    test_case: StatementHeaderKeysTestCase, tmp_path: Path
) -> None:
    (tmp_path / test_case.file_name).write_text(test_case.contents, encoding="utf-8")

    with pytest.raises(ProjectConfigError) as raised:
        load_project_config(project_dir=tmp_path)

    assert test_case.expected_error in raised.value.message
    assert raised.value.help == test_case.expected_help


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
