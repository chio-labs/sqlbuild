"""CLI helpers for optional external SQL reference integrations."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.main.build_compile_reference_resolver import (
    build_compile_reference_resolver,
)
from sqlbuild.shared.types import ExternalReferenceResolver


def resolve_external_reference_resolver(
    *, discovered_inputs: DiscoveredProjectInputs
) -> ExternalReferenceResolver | None:
    """Build the external reference resolver configured for a discovered project."""

    return build_compile_reference_resolver(
        manifest_contents=(
            None
            if discovered_inputs.dbt_manifest_file is None
            else discovered_inputs.dbt_manifest_file.contents
        )
    )
