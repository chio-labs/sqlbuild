"""Prepare invocation-local SQL expansion evidence for compiler-integrated lint."""

from pathlib import Path

from sqlbuild.compiler.compile.models import SqlExpansionContext
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint._helpers.expansion import build_lint_expansion_context


def build_expansion_context(
    *, project_dir: Path, discovered_inputs: DiscoveredProjectInputs
) -> SqlExpansionContext:
    return build_lint_expansion_context(
        project_dir=project_dir, discovered_inputs=discovered_inputs
    )
