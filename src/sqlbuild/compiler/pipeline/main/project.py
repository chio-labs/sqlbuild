"""Compile a project without building an execution plan."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.shared.types import ExternalReferenceResolver


def compile_project(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    no_sql_validation: bool = False,
    external_reference_resolver: ExternalReferenceResolver | None = None,
) -> CompiledProject:
    """Compile discovered inputs into a target-defaulted project view."""

    return build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        external_reference_resolver=external_reference_resolver,
    )
