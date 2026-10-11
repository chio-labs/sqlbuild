from dataclasses import dataclass


@dataclass(frozen=True)
class HandoffTestCase:
    description: str
    args: tuple[str, ...]
    expected_exit_code: int


@dataclass(frozen=True)
class TextReuseTestCase:
    description: str
    args: tuple[str, ...]
    expected_notice: bytes


@dataclass(frozen=True)
class JsonReuseTestCase:
    description: str
    args: tuple[str, ...]
    expected_hits: int


@dataclass(frozen=True)
class EditedProjectTestCase:
    description: str
    args: tuple[str, ...]
    old_text: str
    new_text: str
    expected_misses: int
    expected_fragment: str


@dataclass(frozen=True)
class SelectorFileTestCase:
    description: str
    selectors: str
    expected_records: int
