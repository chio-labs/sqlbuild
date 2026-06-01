from dataclasses import dataclass


@dataclass(frozen=True)
class PythonRelationTargetsTestCase:
    description: str
    expected_source_relation: str
