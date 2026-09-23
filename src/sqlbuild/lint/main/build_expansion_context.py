"""Prepare invocation-local SQL expansion evidence for compiler-integrated lint."""

from pathlib import Path

from sqlbuild.compiler.compile.models import DeclarationScopeBuild, SqlExpansionContext
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint._helpers.expansion import build_lint_expansion_context


def build_expansion_context(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    declaration_scope: DeclarationScopeBuild | None = None,
) -> SqlExpansionContext:
    return build_lint_expansion_context(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        declaration_scope=declaration_scope,
    )
