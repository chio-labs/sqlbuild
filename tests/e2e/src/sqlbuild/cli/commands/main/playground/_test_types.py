from dataclasses import dataclass


@dataclass(frozen=True)
class PythonNodesPlaygroundLifecycleTestCase:
    description: str
    project_name: str
    expected_plan_fragments: tuple[str, ...]
    expected_build_fragments: tuple[str, ...]
    expected_check_fragments: tuple[str, ...]


@dataclass(frozen=True)
class PlaygroundCompileBuildTestCase:
    description: str
    template: str
    project_subdir: str
    expected_build_fragments: tuple[str, ...]


@dataclass(frozen=True)
class UnicodeEmptyFixtureTestCase:
    description: str
    status: str
    expected_added_findings: int = 0


@dataclass(frozen=True)
class LegacyCodePageOutputTestCase:
    description: str
    code_page: str
    expected_summary: str
    expected_json_command: str
