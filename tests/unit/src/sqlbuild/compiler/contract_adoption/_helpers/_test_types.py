from dataclasses import dataclass


@dataclass(frozen=True)
class DynamicContractAdoptionTestCase:
    description: str
    expected_reason: str | None = None
    expected_matching_findings: int = 0
    expected_mismatching_findings: int = 0
