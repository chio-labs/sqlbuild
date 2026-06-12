from dataclasses import dataclass


@dataclass(frozen=True)
class NodeResultSerializationTestCase:
    description: str
    value: object
    expected_encoded: str


@dataclass(frozen=True)
class NodeResultSerializationErrorTestCase:
    description: str
    value: object
    expected_error_fragment: str


@dataclass(frozen=True)
class NodeResultReadTestCase:
    description: str
    metadata_json_b64: str
    expected_metadata: dict[str, object]
