from dataclasses import dataclass


@dataclass(frozen=True)
class BuildQualifiedNameTestCase:
    description: str
    database: str | None
    schema: str | None
    name: str
    expected_qualified: str
