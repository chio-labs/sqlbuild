from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.compiler.node_source_watermarks.exceptions import (
    NodeSourceWatermarkInputError,
)
from sqlbuild.compiler.node_source_watermarks.main.decode_payload import (
    decode_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.main.encode_payload import (
    encode_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkPayload,
    SourceWatermarkEntry,
    UnknownSourceWatermarkEntry,
)
from tests.unit.src.sqlbuild.compiler.node_source_watermarks.main.shared._helpers._test_types import (  # noqa: E501
    InvalidWatermarkPayloadTestCase,
    WatermarkPayloadRoundTripTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        WatermarkPayloadRoundTripTestCase(
            description="round trips structured source and unknown entries",
            expected_source_name="hkjc.events",
            expected_unknown_reason="missing_upstream_watermark",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_watermark_payload_when_encoded_and_decoded_then_preserves_structured_entries(
    test_case: WatermarkPayloadRoundTripTestCase,
) -> None:
    payload: NodeSourceWatermarkPayload = NodeSourceWatermarkPayload(
        version=1,
        complete=False,
        sources=(
            SourceWatermarkEntry(
                source_name=test_case.expected_source_name,
                target_database=None,
                target_schema="main",
                target_name="dev",
                strategy="adapter_metadata",
                value_kind="timestamp",
                data_version="2026-06-29T15:37:00",
                data_version_hash="abc123",
                observed_at=datetime(2026, 6, 29, 15, 38),
                watermark_kind="direct",
            ),
        ),
        unknown_sources=(
            UnknownSourceWatermarkEntry(
                source_name="hkjc.late_feed",
                target_database=None,
                target_schema="main",
                target_name="dev",
                reason=test_case.expected_unknown_reason,
            ),
        ),
    )

    result: NodeSourceWatermarkPayload = decode_watermark_payload(
        value=encode_watermark_payload(payload), qualified_name="analytics._watermarks"
    )

    assert result.version == 1
    assert result.complete is False
    assert result.sources[0].source_name == test_case.expected_source_name
    assert result.unknown_sources[0].reason == test_case.expected_unknown_reason


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidWatermarkPayloadTestCase(
            description="rejects non-base64 payloads",
            raw_payload="not base64",
            expected_error_fragment="base64-encoded JSON",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_watermark_payload_when_decoding_then_raises_input_error(
    test_case: InvalidWatermarkPayloadTestCase,
) -> None:
    with pytest.raises(NodeSourceWatermarkInputError) as exc_info:
        decode_watermark_payload(
            value=test_case.raw_payload, qualified_name="analytics._watermarks"
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
