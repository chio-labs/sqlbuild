from dataclasses import dataclass


@dataclass(frozen=True)
class OpenConnectionSuccessTestCase:
    description: str
    connection_config: dict[str, object]
    monotonic_times: tuple[float, float]
    expected_event_order: tuple[str, ...]
    expected_elapsed_seconds: float
    expected_connection_count: int


@dataclass(frozen=True)
class OpenConnectionFailureTestCase:
    description: str
    connection_config: dict[str, object]
    monotonic_times: tuple[float, float]
    expected_error: Exception
    expected_event_order: tuple[str, ...]
    expected_elapsed_seconds: float
    expected_connection_count: int
