"""Public entrypoint for custom prepare_version loading."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.discovery.models import DiscoveredMaterializationFile
from sqlbuild.compiler.pipeline.helpers.materializations import (
    load_custom_prepare_version_functions as _load_custom_prepare_version_functions,
)


def load_custom_prepare_version_functions(
    materialization_files: tuple[DiscoveredMaterializationFile, ...],
) -> dict[str, Callable[..., None]]:
    """Load optional custom prepare_version callables from discovered project files."""

    return _load_custom_prepare_version_functions(materialization_files)
