from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceLoaderStrategiesE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_countries: tuple[tuple[object, ...], ...]
    expected_webhook_event_counts: tuple[tuple[object, ...], ...]
    expected_order_events: tuple[tuple[object, ...], ...]
    expected_customers: tuple[tuple[object, ...], ...]
    expected_loader_status: tuple[tuple[object, ...], ...]
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_return_code: int = 0
