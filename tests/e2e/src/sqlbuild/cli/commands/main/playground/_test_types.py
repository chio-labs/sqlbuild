from dataclasses import dataclass


@dataclass(frozen=True)
class PythonNodesPlaygroundLifecycleTestCase:
    description: str
    project_name: str
    expected_plan_fragments: tuple[str, ...]
    expected_build_fragments: tuple[str, ...]
    expected_check_fragments: tuple[str, ...]


@dataclass(frozen=True)
class UnicodeEmptyFixtureTestCase:
    description: str
    status: str
    expected_added_findings: int = 0
