from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryFooterTestCase:
    description: str
    counts: tuple[tuple[str, int], ...]
    elapsed: str | None
    expected_no_color: str
    expected_color_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CountHeaderTestCase:
    description: str
    text: str
    use_color: bool
    expected_rendered: str


@dataclass(frozen=True)
class CountNounTestCase:
    description: str
    count: int
    singular: str
    plural: str | None
    expected_text: str
