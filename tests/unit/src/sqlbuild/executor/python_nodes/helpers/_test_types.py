from dataclasses import dataclass


@dataclass(frozen=True)
class PythonNodeSchedulerTestCase:
    description: str
    node_names: tuple[str, ...]
    upstream_names: dict[str, tuple[str, ...]]
    downstream_names: dict[str, tuple[str, ...]]
    completion_order: tuple[str, ...]
    expected_initial_ready: tuple[str, ...]
    expected_final_ready: tuple[str, ...]
    expected_final_in_degree: dict[str, int]
