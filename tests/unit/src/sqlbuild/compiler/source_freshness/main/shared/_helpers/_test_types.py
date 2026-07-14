from dataclasses import dataclass


@dataclass(frozen=True)
class BuildSourceFreshnessSqlTestCase:
    description: str
    database: str | None
    schema: str
    expected_contains: tuple[str, ...]
    transient: bool = False
