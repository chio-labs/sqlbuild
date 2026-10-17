from dataclasses import dataclass


@dataclass(frozen=True)
class HostPayloadFactsTestCase:
    description: str
    project_files: dict[str, str]
    expected_dropped_project_fields: frozenset[str]
    expected_dropped_model_fields: frozenset[str]
