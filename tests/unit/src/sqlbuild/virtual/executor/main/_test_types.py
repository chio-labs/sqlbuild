from dataclasses import dataclass


@dataclass(frozen=True)
class VirtualCloneAggregateTestCase:
    description: str
    action: str
    expected_terminal: str
    expected_error_code: str | None


@dataclass(frozen=True)
class VirtualPromoteLifecycleTestCase:
    description: str
    expected_operation_id: str
    expected_event_types: tuple[str, ...]
    expected_state_result_calls: int
