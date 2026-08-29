from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledObjectKey


@dataclass(frozen=True)
class DeferCloneBoundaryTestCase:
    description: str
    selected_keys: frozenset[CompiledObjectKey]
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_selectors: tuple[str, ...]


@dataclass(frozen=True)
class FunctionDeferCloneBoundaryTestCase:
    description: str
    expected_boundary_selectors: tuple[str, ...]
    expected_view_chain_selectors: tuple[str, ...]
