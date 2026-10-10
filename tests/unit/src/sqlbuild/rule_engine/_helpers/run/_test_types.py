from dataclasses import dataclass


@dataclass(frozen=True)
class PreviewRowsEncodeErrorTestCase:
    """A model config value the preview request builder must reject before custom rules start."""

    description: str
    rejected_value: object
    expected_message: str


@dataclass(frozen=True)
class PreviewRowsMemoTestCase:
    """Whether each preview evaluation reused the memoized response: cold, rebuilt, warm."""

    description: str
    expected_reused: tuple[bool, bool, bool]
