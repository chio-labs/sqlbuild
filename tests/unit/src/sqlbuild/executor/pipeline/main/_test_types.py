from dataclasses import dataclass


@dataclass(frozen=True)
class BuildSchemaPreflightTestCase:
    description: str
    expected_schemas: tuple[tuple[str | None, str], ...]


@dataclass(frozen=True)
class RunnableGraphWidthTestCase:
    description: str
    expected_width: int
