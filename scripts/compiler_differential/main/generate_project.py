"""Generate one deterministic random project for a seed."""

from scripts.compiler_differential.classes.project_builder import ProjectBuilder
from scripts.compiler_differential.models import GeneratedProject


def generate_project(
    *, seed: int, blocks: tuple[str, ...] | None = None, dialect: str | None = None
) -> GeneratedProject:
    """Return the seed's project; `blocks` overrides its blocks, `dialect` its adapter."""

    return ProjectBuilder(seed, blocks=blocks, dialect=dialect).build()
