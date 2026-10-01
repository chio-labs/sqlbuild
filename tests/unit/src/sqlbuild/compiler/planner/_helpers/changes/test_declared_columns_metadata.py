"""Tests for the declared-columns hash recorded in model fingerprint metadata."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.changes.metadata import (
    recorded_declared_columns_hash,
    version_identity_metadata_payload,
    with_declared_columns_hash,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.changes._test_types import (
    DeclaredColumnsMetadataTestCase,
)

_METADATA_JSON: str = '{"config":{"materialized":"table"}}'


@pytest.mark.parametrize(
    "test_case",
    [
        DeclaredColumnsMetadataTestCase(
            description="written hash is read back",
            metadata_json=with_declared_columns_hash(
                metadata_json=_METADATA_JSON, declared_columns_hash="abc123"
            ),
            expected_recorded_hash="abc123",
        ),
        DeclaredColumnsMetadataTestCase(
            description="row written before the key existed has no recorded hash",
            metadata_json=_METADATA_JSON,
            expected_recorded_hash=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_metadata_when_reading_declared_columns_hash_then_tolerates_absence(
    test_case: DeclaredColumnsMetadataTestCase,
) -> None:
    assert recorded_declared_columns_hash(test_case.metadata_json) == (
        test_case.expected_recorded_hash
    )
    assert version_identity_metadata_payload(test_case.metadata_json) == (
        version_identity_metadata_payload(_METADATA_JSON)
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
