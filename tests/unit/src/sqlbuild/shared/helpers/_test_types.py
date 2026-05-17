from dataclasses import dataclass


@dataclass(frozen=True)
class FormatCodedErrorTestCase:
    description: str
    code: str
    message: str
    help: str | None
    use_color: bool
    expected_rendered: str
