from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.unit.src.sqlbuild.adapters.clickhouse._test_types import (
    SessionSettingConflictTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SessionSettingConflictTestCase(
            description="join_use_nulls turned off",
            settings={"join_use_nulls": 0, "max_threads": 4},
            expected_code="A710",
            expected_message=(
                "ClickHouse connection settings override settings SQLBuild requires: join_use_nulls"
            ),
        ),
        SessionSettingConflictTestCase(
            description="two conflicting settings",
            settings={"union_default_mode": "ALL", "mutations_sync": False},
            expected_code="A710",
            expected_message=(
                "ClickHouse connection settings override settings SQLBuild requires: "
                "mutations_sync, union_default_mode"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_user_settings_when_connecting_then_coded_error_names_them(
    test_case: SessionSettingConflictTestCase,
) -> None:
    with pytest.raises(AdapterUserError) as error:
        ClickHouseAdapter().connect(
            {"host": "127.0.0.1", "port": 1, "connect_timeout": 1, "settings": test_case.settings}
        )

    assert (error.value.code, error.value.message) == (
        test_case.expected_code,
        test_case.expected_message,
    )
