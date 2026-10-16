"""Native model file records copy, pickle and construct like the dataclass they replace."""

from __future__ import annotations

import copy
import pickle

import pytest

from sqlbuild._native import DiscoveredSqlModelFile
from tests.integration.src.sqlbuild.compiler.discovery._test_types import RecordCopyTestCase
from tests.integration.src.sqlbuild.compiler.discovery.helpers import model_file_record


@pytest.mark.parametrize(
    "test_case",
    [
        RecordCopyTestCase(
            description="copy.copy",
            copy_record=copy.copy,
            expected_query_sql="select 1 as order_id",
        ),
        RecordCopyTestCase(
            description="copy.deepcopy",
            copy_record=copy.deepcopy,
            expected_query_sql="select 1 as order_id",
        ),
        RecordCopyTestCase(
            description="a pickle round trip",
            copy_record=lambda record: pickle.loads(pickle.dumps(record)),
            expected_query_sql="select 1 as order_id",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_model_file_record_when_copying_then_every_field_is_kept(
    test_case: RecordCopyTestCase,
) -> None:
    record: DiscoveredSqlModelFile = model_file_record()

    copied: DiscoveredSqlModelFile = test_case.copy_record(record)

    assert (copied, copied.query_sql) == (record, test_case.expected_query_sql)
