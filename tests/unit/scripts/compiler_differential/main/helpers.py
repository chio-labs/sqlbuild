"""Helpers for generator and failure corpus tests."""

from __future__ import annotations

from scripts.compiler_differential.main.generate_project import generate_project
from scripts.compiler_differential.models import GeneratedProject


def generated_projects(seeds: range) -> list[GeneratedProject]:
    """Generate one project per seed."""

    return [generate_project(seed=seed) for seed in seeds]


def project_features(projects: list[GeneratedProject]) -> frozenset[str]:
    """Return every feature any project exercises."""

    features: set[str] = set()
    for project in projects:
        features.update(project.features)
    return frozenset(features)


def invalid_count(projects: list[GeneratedProject]) -> int:
    """Count projects generated to fail with a known code."""

    return sum(project.expected_error_code is not None for project in projects)
