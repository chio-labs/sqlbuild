"""Compile profiling constants."""

from sqlbuild.compiler.profiling.types import CompileMetric, CompileTimingPhase

COMPILE_TIMING_PHASES: tuple[CompileTimingPhase, ...] = (
    "attachment_ms",
    "model_analysis_ms",
    "test_input_compile_ms",
    "test_planning_ms",
    "comparison_render_ms",
    "cache_publication_ms",
    "physical_write_ms",
    "stale_traversal_ms",
)

COMPILE_METRICS: tuple[CompileMetric, ...] = (
    "analysis_batch_cache_hits",
    "analysis_entry_cache_hits",
    "analysis_cache_misses",
    "analysis_cache_bypasses",
)
