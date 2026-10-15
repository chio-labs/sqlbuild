//! Every supported phase in milliseconds, then every metric, in stable presentation order.

use crate::compile_timings::constants::{COMPILE_METRICS, COMPILE_TIMING_PHASES};
use crate::compile_timings::models::CompileTimings;

/// Each phase's whole milliseconds and each metric's value, absent ones as zero.
#[must_use]
pub fn compile_timing_milliseconds(timings: &CompileTimings) -> Vec<(&'static str, u64)> {
    let phases = COMPILE_TIMING_PHASES.iter().map(|phase| {
        (
            *phase,
            timings.elapsed_ns.get(*phase).copied().unwrap_or(0) / 1_000_000,
        )
    });
    let metrics = COMPILE_METRICS
        .iter()
        .map(|metric| (*metric, timings.metrics.get(*metric).copied().unwrap_or(0)));
    phases.chain(metrics).collect()
}
