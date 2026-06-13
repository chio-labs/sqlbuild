from dataclasses import dataclass


@dataclass(frozen=True)
class NodeResultReadWriteIntegrationTestCase:
    description: str
    expected_payload: dict[str, object]
    expected_metadata: dict[str, object]
