from dataclasses import dataclass


@dataclass(frozen=True)
class UnreplaceableConnectionTestCase:
    """A timed-out item whose connection can neither be recovered nor replaced."""

    description: str
    later_items: int
    expected_completions: tuple[tuple[str, str], ...]
    expected_reconnect_attempts: int
    expected_maximum_seconds: float
