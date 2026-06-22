from dataclasses import dataclass


@dataclass(frozen=True)
class BuildSchemaPreflightTestCase:
    description: str
    expected_schemas: tuple[tuple[str | None, str], ...]
