from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.lineage.types import ColumnLineageMode


@dataclass(frozen=True)
class GeneratedAnalysisParityTestCase:
    """Seeded generated projects whose model analysis both engines must agree on."""

    description: str
    seed: int
    count: int
    model_count: int
    dialects: tuple[str | None, ...]
    lineage_mode: ColumnLineageMode
    expected_minimum_native: int
    expected_minimum_expression_shapes: int
    expected_minimum_pivot_proofs: int
    expected_minimum_python_cte_recoveries: int
    expected_minimum_legacy_analyses: int
    expected_minimum_proven_pivots: int
    expected_maximum_enrichment_deferrals: int
    expected_minimum_native_enrichments: int


@dataclass(frozen=True)
class AnalysisFallbackTestCase:
    """A project the native session hands back to Python whole, recording why."""

    description: str
    files: dict[str, str]
    allow_compact_analysis: bool
    keeps_catalog: bool
    expected_kind: str


@dataclass(frozen=True)
class SessionFailureTestCase:
    """A session that fails after Python answered deferrals, so Python analyses everything."""

    description: str
    seed: int
    model_count: int
    expected_kinds: dict[str, int]


@dataclass(frozen=True)
class StandalonePivotProofTestCase:
    """A pivot model left out of model analysis, whose proof assembly takes natively."""

    description: str
    analysed_models: frozenset[str]
    expected_native_proofs: int
    expected_proven_by_model: dict[str, bool | None]


@dataclass(frozen=True)
class CteFactRecoveryParityTestCase:
    """Seeded CTE queries whose native and Python CTE fact recoveries must agree."""

    description: str
    seed: int
    count: int
    expected_minimum_compared: int
    expected_minimum_recovered: dict[str, int]
