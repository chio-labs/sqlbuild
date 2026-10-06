"""Test case types for the compile render reuse session and stored model analyses."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompilerDiagnostic


@dataclass(frozen=True)
class RenderReplayTestCase:
    """A reused render and what reusing it must report again."""

    description: str
    model_name: str
    expected_diagnostics: tuple[CompilerDiagnostic, ...]
    expected_environment_names: tuple[str, ...]


@dataclass(frozen=True)
class ReusableModelsTestCase:
    """Stored and current models, and which current models may reuse their stored render."""

    description: str
    stored_models: tuple[str, ...]
    current_models: tuple[str, ...]
    changed_paths: frozenset[str]
    run_id_readers: frozenset[str]
    expected_reusable: dict[str, bool]


@dataclass(frozen=True)
class CorruptRenderTestCase:
    """A stored render payload that cannot be decoded."""

    description: str
    model_name: str
    expected_rendered_again: bool


@dataclass(frozen=True)
class ReleasedRenderTestCase:
    """A reused and an edited render, and which stored bytes storing the compile releases."""

    description: str
    retained_models: frozenset[str]
    expected_released: dict[str, bool]
    expected_query_sqls: dict[str, str]


@dataclass(frozen=True)
class DeclarationReuseTestCase:
    """Paths changed since a stored compile, and whether its declaration files are reused."""

    description: str
    changed_paths: frozenset[str] | None
    recorded_variant: str
    expected_full_discoveries: int


@dataclass(frozen=True)
class StoredAnalysisScopeTestCase:
    """Which renders a compile reused, how analyses were stored, and which may be served."""

    description: str
    reused_models: frozenset[str]
    rekeyed_models: frozenset[str]
    twinned_models: frozenset[str]
    stored_column_types: dict[str, dict[str, str]]
    expected_served: frozenset[str]


@dataclass(frozen=True)
class StaleServedAnalysisTestCase:
    """Final parent signatures in this compile, and which served analyses they make stale."""

    description: str
    current_signatures: dict[str, str]
    expected_stale: set[str]
