from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectDependencyTestCase:
    description: str
    dependency_name: str
    expected_in_core_dependencies: bool
    expected_optional_extra_absent: bool
