"""Generate one deterministic random project for a seed."""

from scripts.compiler_differential.classes.project_builder import ProjectBuilder
from scripts.compiler_differential.models import GeneratedProject


def generate_project(*, seed: int) -> GeneratedProject:
    """Return the same project files and expectation for the same seed on every platform."""

    return ProjectBuilder(seed).build()
