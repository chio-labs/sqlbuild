//! Record the wall time of one compile phase.

use std::time::Instant;

use crate::compile_context::_helpers::active::active;
use crate::compile_context::main::add_compile_timing::add_compile_timing;

/// Record the wall time `body` spans under `phase` when a collector is active.
pub fn record_compile_timing<T, E>(
    phase: &str,
    body: impl FnOnce() -> Result<T, E>,
) -> Result<T, E> {
    if active().is_none() {
        return body();
    }
    let started: Instant = Instant::now();
    let result: Result<T, E> = body();
    add_compile_timing(
        phase,
        u64::try_from(started.elapsed().as_nanos()).unwrap_or(u64::MAX),
    );
    result
}
