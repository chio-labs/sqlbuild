"""Offline construction and persistent loading of canonical project scope facts."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.discovery.main.resolve_adapter import resolve_adapter
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.main._scope_index_with_compile_usages import (
    scope_index_with_compile_usages,
)
from sqlbuild.compiler.compile.models import CompileAdapterContext, CompileProjectInputs
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes._helpers.builder import build_tolerant_scope_index
from sqlbuild.compiler.scopes._helpers.cache import (
    read_cached_scope_index,
    scope_index_fingerprint,
    write_cached_scope_index,
)
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.main.resolve_effective_collection_rendering import (
    resolve_effective_collection_rendering,
)


def load_or_build_scope_index(*, project_dir: Path, no_cache: bool = False) -> ScopeIndex:
    """Load or build scope facts without credentials, a connection, or warehouse access."""

    resolved_project_dir: Path = project_dir.resolve()
    fingerprint: str | None
    try:
        fingerprint = scope_index_fingerprint(project_dir=resolved_project_dir)
    except (OSError, UnicodeError, ValueError):
        fingerprint = None
    if not no_cache and fingerprint is not None:
        cached: ScopeIndex | None = read_cached_scope_index(
            project_dir=resolved_project_dir, fingerprint=fingerprint
        )
        if cached is not None:
            return cached

    try:
        discovered: DiscoveredProjectInputs = discover_project_inputs(
            project_dir=resolved_project_dir,
            extract_output_column_locations=False,
        )
        adapter_name: str = resolve_effective_adapter_name(
            project_config=discovered.project_config,
            local_config=discovered.local_config,
        )
        adapter: BaseAdapter = resolve_adapter(adapter_name=adapter_name)
        compile_inputs: CompileProjectInputs = build_compile_inputs(
            discovered_inputs=discovered,
            adapter_context=CompileAdapterContext(
                value_renderer=adapter,
                collection_rendering=resolve_effective_collection_rendering(
                    project_config=discovered.project_config,
                    declaration_override=None,
                ),
                python_functions_inherit_default_namespace=(
                    adapter.python_functions_inherit_default_namespace()
                ),
            ),
            resolved_connection={},
            no_sql_validation=True,
            defer_model_sql_validation=True,
            no_cache=True,
        )
        index: ScopeIndex = scope_index_with_compile_usages(inputs=compile_inputs)
    except (OSError, UnicodeError, ValueError, ImportError):
        index = build_tolerant_scope_index(project_dir=resolved_project_dir)

    if not no_cache and fingerprint is not None:
        write_cached_scope_index(
            project_dir=resolved_project_dir, fingerprint=fingerprint, index=index
        )
    return index
