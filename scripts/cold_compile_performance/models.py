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
