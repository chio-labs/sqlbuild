"""Custom materialization loading from discovered project files."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlbuild._native import DiscoveredMaterializationFile, PlannerInputError
from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult
from sqlbuild.runtime.user_code.main.user_code_spec import user_code_spec


def load_custom_materializations(
    materialization_files: tuple[DiscoveredMaterializationFile, ...],
) -> dict[str, Callable[[MaterializationContext], MaterializationResult]]:
    """Import discovered materialization modules and extract materialize callables."""

    registry: dict[str, Callable[[MaterializationContext], MaterializationResult]] = {}
    mat_file: DiscoveredMaterializationFile
    for mat_file in materialization_files:
        file_path: Path = Path(mat_file.file_path)
        spec: Any = user_code_spec(name=mat_file.name, file_path=file_path, root=file_path.parent)
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
