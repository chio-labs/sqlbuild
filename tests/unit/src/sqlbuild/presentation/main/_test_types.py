from dataclasses import dataclass


@dataclass(frozen=True)
class FormatCodedErrorTestCase:
    description: str
    code: str
    message: str
    help: str | None
    use_color: bool
    expected_rendered: str
    include_error_label: bool = True


@dataclass(frozen=True)
class SummaryFooterTestCase:
    description: str
    counts: tuple[tuple[str, int], ...]
    elapsed: str | None
    expected_no_color: str
    expected_color_fragments: tuple[str, ...]


@dataclass(frozen=True)
class InlineErrorLinesTestCase:
    description: str
    content_width: int
    expected_lines: list[str]
