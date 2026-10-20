//! Add elapsed time to one compile phase.

use crate::compile_context::_helpers::active::active;

/// Add elapsed nanoseconds to a phase when a collector is active.
pub fn add_compile_timing(phase: &str, elapsed_ns: u64) {
    if let Some(collector) = active() {
        *collector
            .borrow_mut()
            .elapsed_ns
            .entry(phase.to_owned())
            .or_default() += elapsed_ns;
    }
}
