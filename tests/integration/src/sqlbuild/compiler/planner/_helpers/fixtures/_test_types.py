from dataclasses import dataclass


@dataclass(frozen=True)
class FixtureTypeScopeTestCase:
    description: str
    unrelated_relations: int
    expected_eager_relations: int = 1
    expected_eager_columns: int = 2
