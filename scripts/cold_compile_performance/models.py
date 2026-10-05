"""Structural measurements for generated compiler performance workloads."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VariedProjectStatistics:
    model_count: int
    distinct_operator_shapes: int
    model_edges: int
    largest_component: int
    maximum_depth: int
    leaf_models: int
    array_models: int
    window_models: int


@dataclass(frozen=True)
class RandomDagProject:
    """One seeded DuckDB project whose models bind against inferred upstream shapes."""

    seed: int
    model_count: int
    errors: bool = False
    run_ids: bool = False
    analysis_opt_outs: bool = False
    missing_reference: bool = False
    cycle: bool = False
    rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class RandomRenderProject:
    """One seeded project mixing macros, declarations, variables, and dialect-specific text."""

    seed: int
    model_count: int
    adapter: str = "duckdb"
    errors: int = 0
    generated_references: bool = False
