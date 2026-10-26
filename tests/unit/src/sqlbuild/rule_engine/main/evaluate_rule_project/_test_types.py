"""Test case declarations for project rules under the public harness."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectRulesDirectoryTestCase:
    description: str
    extra_project_files: dict[str, str]
    case_files: tuple[tuple[str, str], ...]
    expected_finding_count: int
