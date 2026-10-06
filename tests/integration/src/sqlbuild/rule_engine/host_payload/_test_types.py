from dataclasses import dataclass


@dataclass(frozen=True)
class HostPayloadFactsTestCase:
    description: str
    project_files: dict[str, str]
    expected_unpopulated_trimmed_fields: frozenset[str]
