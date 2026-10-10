"""Find Python strings that name a model or column a refactoring renames."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.refactoring._helpers.project.project_files import python_string_locations
from sqlbuild.compiler.refactoring.models import ManualLocation


def find_python_string_locations(
    *,
    project_dir: Path,
    discovered: DiscoveredProjectInputs,
    names: tuple[str, ...],
    reason: str,
    context: str | None = None,
) -> tuple[ManualLocation, ...]:
    """Flag Python strings that name a model or column; with context, only SQL naming it too."""

    return python_string_locations(
        project_dir=project_dir,
        discovered=discovered,
        names=names,
        reason=reason,
        context=context,
    )
