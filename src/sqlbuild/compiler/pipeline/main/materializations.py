"""Public entrypoint for custom materialization loading."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.discovery.models import DiscoveredMaterializationFile
from sqlbuild.compiler.pipeline._helpers.materializations import (
    load_custom_materializations as _load_custom_materializations,
)
from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult


def load_custom_materializations(
    materialization_files: tuple[DiscoveredMaterializationFile, ...],
) -> dict[str, Callable[[MaterializationContext], MaterializationResult]]:
    """Load custom materialization callables from discovered project files."""

    return _load_custom_materializations(materialization_files)
