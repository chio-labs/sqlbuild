"""Discovery helpers for declarative integration loaders."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction, DiscoveredSourceFile


def build_integration_loader_functions(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> tuple[DiscoveredLoaderFunction, ...]:
    """Build synthetic loader functions for declarative integration loaders."""

    from sqlbuild.integrations.dlt.main.loaders import build_dlt_loader_functions
    from sqlbuild.integrations.ingestr.main.loaders import build_ingestr_loader_functions

    return build_ingestr_loader_functions(source_files) + build_dlt_loader_functions(source_files)
