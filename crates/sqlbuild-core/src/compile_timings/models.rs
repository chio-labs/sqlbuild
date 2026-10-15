//! Accumulated compile timings.

use std::collections::HashMap;

/// Elapsed nanoseconds per phase and summed values per metric of one compile invocation.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CompileTimings {
    pub elapsed_ns: HashMap<String, u64>,
    pub metrics: HashMap<String, u64>,
}
