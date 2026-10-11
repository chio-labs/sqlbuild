from dataclasses import dataclass


@dataclass(frozen=True)
class NativeRowsEncodeErrorTestCase:
    """A model config value the native request builder must reject before custom rules start."""

    description: str
    rejected_value: object
    expected_message: str


@dataclass(frozen=True)
class NativeRowsMemoTestCase:
    """Whether each native evaluation reused the memoized response: cold, rebuilt, warm."""

    description: str
    expected_reused: tuple[bool, bool, bool]
