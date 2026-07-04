from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.run.helpers.reuse.core import create_relation_from_reuse_origin
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    RelationReuseOriginExecutionTestCase,
)
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import FakeRelationReuseAdapter


@pytest.mark.parametrize(
    "test_case",
    (
        RelationReuseOriginExecutionTestCase(
            description="hard copy uses CTAS without cheap support probe",
            hard_copy=True,
            supports_zero_copy_clone=True,
            expected_calls=("create_table_as",),
            expected_sql="SELECT * FROM prod.orders",
        ),
        RelationReuseOriginExecutionTestCase(
            description="cheap reuse uses clone when adapter supports zero copy",
            hard_copy=False,
            supports_zero_copy_clone=True,
            expected_calls=("supports_zero_copy_clone", "clone"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_relation_reuse_origin_when_creating_relation_then_uses_expected_copy_mode(
    test_case: RelationReuseOriginExecutionTestCase,
) -> None:
    adapter: FakeRelationReuseAdapter = FakeRelationReuseAdapter(
        supports_zero_copy_clone=test_case.supports_zero_copy_clone
    )
    recorder: StatementRecorder = StatementRecorder()

    create_relation_from_reuse_origin(
        adapter=adapter,
        connection=object(),
        origin_relation="prod.orders",
        destination_relation="dev.orders",
        hard_copy=test_case.hard_copy,
        statement_recorder=recorder,
    )

    assert tuple(adapter.calls) == test_case.expected_calls
    assert adapter.sql == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        RelationReuseOriginExecutionTestCase(
            description="cheap reuse fails clearly when adapter does not support zero copy",
            hard_copy=False,
            supports_zero_copy_clone=False,
            expected_calls=("supports_zero_copy_clone",),
            expected_error_fragments=(
                "target 'dev' has reuse_from = 'prod'",
                "adapter 'fake_relation_reuse' does not support cheap relation reuse",
                "reuse_hard_copy = false",
                "will not copy production relations automatically",
                "reuse_hard_copy = true",
                "remove reuse_from to build normally",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_relation_reuse_origin_when_cheap_reuse_is_unsupported_then_it_raises(
    test_case: RelationReuseOriginExecutionTestCase,
) -> None:
    adapter: FakeRelationReuseAdapter = FakeRelationReuseAdapter(
        supports_zero_copy_clone=test_case.supports_zero_copy_clone
    )
    recorder: StatementRecorder = StatementRecorder()

    with pytest.raises(ExecutorInputError) as exc_info:
        create_relation_from_reuse_origin(
            adapter=adapter,
            connection=object(),
            origin_relation="prod.orders",
            destination_relation="dev.orders",
            hard_copy=test_case.hard_copy,
            statement_recorder=recorder,
            destination_target_name="dev",
            reuse_from_target_name="prod",
        )

    for fragment in test_case.expected_error_fragments:
        assert fragment in str(exc_info.value)
    assert tuple(adapter.calls) == test_case.expected_calls
