from dataclasses import dataclass


@dataclass(frozen=True)
class ReadTextTestCase:
    description: str
    path: str
    expected_text: str | None = None
    expected_error: str = ""


@dataclass(frozen=True)
class TreeQueryTestCase:
    description: str
    argument: str
    expected_values: tuple[str, ...]


@dataclass(frozen=True)
class RelativePartsTestCase:
    description: str
    path: str
    under: str
    expected_parts: tuple[str, ...] | None = None
    expected_error: str = ""
