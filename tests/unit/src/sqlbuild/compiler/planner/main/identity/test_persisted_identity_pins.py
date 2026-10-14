"""Version identities are persisted in warehouse state; these values must never change."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import (
    build_function_local_hashes,
    build_seed_identity,
    build_version_identity_metadata_json,
    declared_columns_hash,
)
from tests.unit.src.sqlbuild.compiler.planner.main.identity._test_types import (
    PersistedIdentityTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.main.identity.helpers import (
    build_contract_model,
    build_identity_function,
    build_identity_seed,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PersistedIdentityTestCase(
            description="version identity metadata",
            build=lambda _: build_version_identity_metadata_json(
                model_name="orders",
                config_values={
                    "materialized": "table",
                    "batch_size": 10,
                    "lookback": 1.5,
                    "unique_key": ("id", "café"),
                    "cursor_inputs": {"b": None, "a": True},
                    "ignored": 1,
                },
                local_function_hashes={"f": "h"},
            ),
            expected_identity=(
                '{"config":{"batch_size":10,"cursor_inputs":{"a":true,"b":null},'
                '"lookback":1.5,"materialized":"table","unique_key":["id","caf\\u00e9"]},'
                '"execution_signature":{},"local_function_hashes":{"f":"h"},"model_name":"orders"}'
            ),
        ),
        PersistedIdentityTestCase(
            description="declared columns hash",
            build=lambda _: declared_columns_hash(model=build_contract_model()),
            expected_identity="fd43639fd4c7a585e25ad4bc134d59e890cb81f34f87c7083bfbb83a7c5a45c9",
        ),
        PersistedIdentityTestCase(
            description="function local hash",
            build=lambda _: build_function_local_hashes(
                functions=(build_identity_function(),), dialect="duckdb"
            ),
            expected_identity={
                "add_one": "f0b98ef7f39ec80c918937418d5d1b13c01407d83846e9817ce4402748d74d97"
            },
        ),
        PersistedIdentityTestCase(
            description="seed identity",
            build=lambda directory: build_seed_identity(build_identity_seed(directory)),
            expected_identity=(
                "37b6c31dd600a9c5b2f811338382d211faa6b7278e6e552cec636fdabf243323",
                '{"columns":[{"name":"id","nullable":null,"type":"int"}],"csv_settings":'
                '{"delimiter":null,"doublequote":null,"encoding":null,"escapechar":null,'
                '"keep_default_na":null,"lineterminator":null,"na_values":null,"quotechar":null,'
                '"skipinitialspace":null},"name":"regions","rows":[["id","name"],["1","caf\\u00e9"]]}',
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fixed_inputs_when_building_identities_then_matches_pinned_values(
    test_case: PersistedIdentityTestCase, tmp_path: Path
) -> None:
    assert test_case.build(tmp_path) == test_case.expected_identity


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
