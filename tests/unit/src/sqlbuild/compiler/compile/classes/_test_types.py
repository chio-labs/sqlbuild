"""Test case types for compile classes."""

from __future__ import annotations

from collections.abc import Callable
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
class MacroCallMemoTestCase:
    """A macro's output and whether the memo may replay it."""

    description: str
    macro_sql: str
    expected_remembered: bool


@dataclass(frozen=True)
class MacroCallReadsTestCase:
    """A first macro call's input reads, which a replay must report for the next model."""

    description: str
    macro_call: Callable[[], None]
    expected_environment_names: tuple[str, ...]
    expected_read_run_id: bool


@dataclass(frozen=True)
class MacroCallDiagnosticTestCase:
    """A first macro call, and whether the memo may replay it for the next model."""

    description: str
    macro_call: Callable[[], None]
    expected_remembered: bool
