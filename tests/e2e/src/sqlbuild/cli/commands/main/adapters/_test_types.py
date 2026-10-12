from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectLocalAdapterCliTestCase:
    description: str
    command: tuple[str, ...]
    expected_stdout_fragment: str
    expected_return_code: int = 0


@dataclass(frozen=True)
class ProjectLocalRenderingTestCase:
    description: str
    expected_marker_rows: list[tuple[object, ...]]
    expected_model_rows: list[tuple[object, ...]]
