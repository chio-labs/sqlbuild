from dataclasses import dataclass


@dataclass(frozen=True)
class SourceFreshnessAgePolicyDurationTestCase:
    description: str
    warn_after: str
    expected_error_fragment: str
