from dataclasses import dataclass


@dataclass(frozen=True)
class WatermarkPayloadRoundTripTestCase:
    description: str
    expected_source_name: str
    expected_unknown_reason: str


@dataclass(frozen=True)
class InvalidWatermarkPayloadTestCase:
    description: str
    raw_payload: str
    expected_error_fragment: str
