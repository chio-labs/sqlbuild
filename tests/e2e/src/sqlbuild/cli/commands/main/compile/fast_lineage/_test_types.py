from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeFastLineageCliTestCase:
    """Every engine compiling and tracing fast lineage of one project through the CLI."""

    description: str
    files: dict[str, str]
    lineage_targets: tuple[str, ...]
    expected_lineage: dict[str, dict[str, object]]
    expected_minimum_python_fallback_parses: int
    expected_minimum_traced_edges: int


@dataclass(frozen=True)
class NativeRichLineageCliTestCase:
    """The wheel and the native engine compiling and tracing rich lineage of one project."""

    description: str
    files: dict[str, str]
    lineage_targets: tuple[str, ...]
    expected_wheel_analyses: int
    expected_native_models: int
    expected_minimum_traced_edges: int
