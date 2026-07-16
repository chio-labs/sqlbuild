from dataclasses import dataclass


@dataclass(frozen=True)
class FormatCodedErrorTestCase:
    description: str
    code: str
    message: str
    help: str | None
    use_color: bool
    expected_rendered: str


@dataclass(frozen=True)
class SummaryFooterTestCase:
    description: str
    counts: tuple[tuple[str, int], ...]
    elapsed: str | None
    expected_no_color: str
    expected_color_fragments: tuple[str, ...]
