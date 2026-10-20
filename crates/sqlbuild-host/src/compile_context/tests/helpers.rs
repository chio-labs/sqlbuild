use sqlbuild_core::compile_timings::models::CompileTimings;

use crate::compile_context::main::add_compile_timing::add_compile_timing;
use crate::compile_context::main::collect_compile_timings::collect_compile_timings;
use crate::compile_context::main::record_compile_cpu_timing::record_compile_cpu_timing;
use crate::compile_context::main::record_compile_metric::record_compile_metric;
use crate::compile_context::main::record_compile_timing::record_compile_timing;
use crate::compile_context::main::timing_milliseconds::timing_milliseconds;
use crate::compile_context::tests::test_types::SteppingClock;

/// Record one timing, one CPU timing, two metric values and one wall timing.
fn record_all(clock: &SteppingClock) -> Result<(), ()> {
    add_compile_timing("attachment_ms", 2_000_000);
    record_compile_cpu_timing(clock, "model_analysis_cpu_ms", || Ok(()))?;
    record_compile_metric("analysis_cache_misses", 3);
    record_compile_metric("analysis_cache_misses", -1);
    record_compile_timing("test_planning_ms", || Ok(()))
}

/// The timings `record_all` leaves in a collection around it.
pub(super) fn collected(clock: &SteppingClock) -> Option<CompileTimings> {
    collect_compile_timings(|collector| {
        record_all(clock)?;
        Ok::<_, ()>(collector.borrow().clone())
    })
    .ok()
}

/// No timings: `record_all` runs outside any collection.
pub(super) fn uncollected(clock: &SteppingClock) -> Option<CompileTimings> {
    record_all(clock).ok().and(None)
}

/// The outer collection's first phase in milliseconds after a nested collection ends.
pub(super) fn outer_attachment_ms(inner_ns: u64, outer_ns: u64) -> Option<u64> {
    collect_compile_timings(|outer| {
        collect_compile_timings(|_inner| {
            add_compile_timing("attachment_ms", inner_ns);
            Ok::<(), ()>(())
        })?;
        add_compile_timing("attachment_ms", outer_ns);
        Ok::<_, ()>(timing_milliseconds(outer)[0].1)
    })
    .ok()
}
