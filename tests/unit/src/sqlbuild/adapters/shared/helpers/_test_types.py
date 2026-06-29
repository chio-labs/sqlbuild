from dataclasses import dataclass


@dataclass(frozen=True)
class RenderNodeSourceWatermarkSqlTestCase:
    description: str
    expected_contains: tuple[str, ...]
