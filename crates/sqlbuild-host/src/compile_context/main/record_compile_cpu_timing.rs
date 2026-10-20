//! Record the process CPU time of one compile phase.

use crate::compile_context::_helpers::active::active;
use crate::compile_context::main::add_compile_timing::add_compile_timing;
use crate::compile_context::types::ProcessClock;

/// Record the process CPU time `body` spans, including its worker threads, under `phase`.
pub fn record_compile_cpu_timing<C: ProcessClock, T>(
    clock: &C,
    phase: &str,
    body: impl FnOnce() -> Result<T, C::Error>,
) -> Result<T, C::Error> {
    if active().is_none() {
        return body();
    }
    let started: u64 = clock.process_time_ns()?;
    let result: Result<T, C::Error> = body();
    let ended: u64 = clock.process_time_ns()?;
    add_compile_timing(phase, ended.saturating_sub(started));
    result
}
