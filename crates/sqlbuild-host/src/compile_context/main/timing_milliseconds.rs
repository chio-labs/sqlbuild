//! A collector's timings as `--json` reports them.

use sqlbuild_core::compile_timings::main::compile_timing_milliseconds::compile_timing_milliseconds;

use crate::compile_context::types::CompileTimingsHandle;

/// Every reported phase in milliseconds, then every metric.
#[must_use]
pub fn timing_milliseconds(collector: &CompileTimingsHandle) -> Vec<(&'static str, u64)> {
    compile_timing_milliseconds(&collector.borrow())
}
