from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.lineage.types import ColumnLineageMode


@dataclass(frozen=True)
class GeneratedAnalysisTestCase:
    """Seeded generated projects whose uncached, cached and re-proven native analyses agree."""

    description: str
    seed: int
    count: int
    model_count: int
    inference_profiles: tuple[ExpressionInferenceProfile, ...]
    extra_files: dict[str, str]
    lineage_mode: ColumnLineageMode
    expected_minimum_native: int
    expected_minimum_expression_shapes: int
    expected_minimum_pivot_proofs: int
    expected_minimum_proven_pivots: int
    expected_minimum_native_enrichments: int


@dataclass(frozen=True)
class InternalFailureTestCase:
    """A project whose native analysis fails internally, and the error the compile raises."""

    description: str
    files: dict[str, str]
    expected_message: str


@dataclass(frozen=True)
class CyclicAnalysisTestCase:
    """Models that `ref` each other, which the native session analyses in one unordered wave."""

    description: str
    files: dict[str, str]
    dialects: tuple[str, ...]
    lineage_modes: tuple[ColumnLineageMode, ...]
    expected_analysed: int


@dataclass(frozen=True)
class CyclicCompileTestCase:
    """A project whose models `ref` each other, compiled through the CLI."""

    description: str
    files: dict[str, str]
    expected_exit_code: int
    expected_compiled: tuple[str, ...]


@dataclass(frozen=True)
class StandalonePivotProofTestCase:
    """A pivot model left out of model analysis, whose proof assembly takes natively."""

    description: str
    analysed_models: frozenset[str]
    expected_native_proofs: int
    expected_session_proofs: int
    expected_proven_by_model: dict[str, bool | None]


@dataclass(frozen=True)
class SharedAnalysisTestCase:
    """Models whose equal queries share one analysis, some inexact and so re-analysed alone."""

    description: str
    regions: tuple[str, ...]
    inexact_regions: tuple[str, ...]
    dialects: tuple[str | None, ...]
    expected_analysed: int
    expected_shared: int
    expected_reanalysed: int
    expected_unshared: int
    expected_column_values: int


@dataclass(frozen=True)
class CteFactRecoveryParityTestCase:
    """Seeded CTE queries whose native and Python CTE fact recoveries must agree."""

    description: str
    seed: int
    count: int
    expected_minimum_compared: int
    expected_minimum_recovered: dict[str, int]


@dataclass(frozen=True)
class AdapterRuleCallbackTestCase:
    """A project-local adapter rule the native session calls back into, and what it raises."""

    description: str
    seed: int
    model_count: int
    raised: type[Exception] | None
    expected_minimum_calls: int


@dataclass(frozen=True)
class SharedQueryOutputTestCase:
    """Models with equal query shapes over different inputs, and each model's own outputs."""

    description: str
    models: dict[str, str]
    expected_lineage: tuple[tuple[str, str, str], ...] = ()
    expected_findings: tuple[tuple[str, str], ...] = ()
