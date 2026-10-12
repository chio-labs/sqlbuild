"""Compile-equivalent description resolution for header-only tooling."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.main._model_description_inputs import (
    discover_model_description_inputs,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, ModelSchemaDeclaration


class ModelDescriptionResolution:
    """Resolve model descriptions that come from outside the MODEL header."""

    @staticmethod
    def externally_described_models(*, project_dir: Path) -> frozenset[Path]:
        """Return model files that `[defaults]`, `[path_defaults]` or a model schema describe."""

        discovered_inputs: DiscoveredProjectInputs = discover_model_description_inputs(
            project_dir=project_dir
        )
        model_schemas: dict[str, ModelSchemaDeclaration] = _native.public_model_schema_index(
            discovered_inputs
        )
        return frozenset(_native.externally_described_models(discovered_inputs, model_schemas))
