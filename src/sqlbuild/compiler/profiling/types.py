"""Compile profiling type aliases."""

from typing import Literal

type CompileTimingPhase = Literal[
    "attachment_ms",
    "model_analysis_ms",
    "test_input_compile_ms",
    "test_planning_ms",
    "comparison_render_ms",
    "cache_publication_ms",
    "physical_write_ms",
    "stale_traversal_ms",
]
