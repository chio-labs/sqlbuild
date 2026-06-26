from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models.core import CompiledObjectKey


@dataclass(frozen=True)
class DeferCloneBoundaryTestCase:
    description: str
    selected_keys: frozenset[CompiledObjectKey]
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_selectors: tuple[str, ...]
