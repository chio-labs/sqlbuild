"""Compile-equivalent description resolution for header-only tooling."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    has_resolved_model_description,
)
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_public_model_schema_index,
)
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
        model_schemas: dict[str, ModelSchemaDeclaration] = build_public_model_schema_index(
            discovered_inputs=discovered_inputs
        )
        return frozenset(
            model_file.file_path
            for model_file in discovered_inputs.model_files
            if has_resolved_model_description(
                model_file=model_file,
                defaults=discovered_inputs.project_config.defaults,
                path_defaults=discovered_inputs.project_config.path_defaults,
                model_schemas=model_schemas,
            )
        )
