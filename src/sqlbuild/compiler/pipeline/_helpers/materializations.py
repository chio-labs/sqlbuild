"""Custom materialization loading from discovered project files."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from types import ModuleType
from typing import Any

from sqlbuild.compiler.discovery.models import DiscoveredMaterializationFile
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult


def load_custom_materializations(
    materialization_files: tuple[DiscoveredMaterializationFile, ...],
) -> dict[str, Callable[[MaterializationContext], MaterializationResult]]:
    """Import discovered materialization modules and extract materialize callables."""

    registry: dict[str, Callable[[MaterializationContext], MaterializationResult]] = {}
    mat_file: DiscoveredMaterializationFile
    for mat_file in materialization_files:
        spec: Any = importlib.util.spec_from_file_location(mat_file.name, mat_file.file_path)
        if spec is None or spec.loader is None:
            raise PlannerInputError(
                f"materialization '{mat_file.name}' at {mat_file.file_path} "
                f"could not be loaded as a Python module"
            )
        module: ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        materialize_fn: Any = getattr(module, "materialize", None)
        if materialize_fn is None or not callable(materialize_fn):
            raise PlannerInputError(
                f"materialization '{mat_file.name}' at {mat_file.file_path} "
                f"must define a callable 'materialize' function"
            )
        registry[mat_file.name] = materialize_fn
    return registry


def load_custom_prepare_version_functions(
    materialization_files: tuple[DiscoveredMaterializationFile, ...],
) -> dict[str, Callable[..., None]]:
    """Import discovered materialization modules and extract optional prepare_version callables."""

    registry: dict[str, Callable[..., None]] = {}
    mat_file: DiscoveredMaterializationFile
    for mat_file in materialization_files:
        spec: Any = importlib.util.spec_from_file_location(mat_file.name, mat_file.file_path)
        if spec is None or spec.loader is None:
            raise PlannerInputError(
                f"materialization '{mat_file.name}' at {mat_file.file_path} "
                f"could not be loaded as a Python module"
            )
        module: ModuleType = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        prepare_version_fn: Any = getattr(module, "prepare_version", None)
        if prepare_version_fn is None:
            continue
        if not callable(prepare_version_fn):
            raise PlannerInputError(
                f"materialization '{mat_file.name}' at {mat_file.file_path} "
                f"defines a non-callable 'prepare_version' attribute"
            )
        registry[mat_file.name] = prepare_version_fn
    return registry
