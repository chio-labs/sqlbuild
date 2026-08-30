from dataclasses import dataclass


@dataclass(frozen=True)
class PrMetadataValidationTestCase:
    description: str
    branch: str
    title: str
    body: str
    expected_errors: tuple[str, ...]
