use std::cell::Cell;

use sqlbuild_core::compile_timings::models::CompileTimings;

use crate::compile_context::types::ProcessClock;

pub(super) struct RecordingTestCase {
    pub(super) description: &'static str,
    pub(super) run: fn(&SteppingClock) -> Option<CompileTimings>,
    pub(super) expected_elapsed_ns: Option<u64>,
    pub(super) expected_cpu_ns: Option<u64>,
    pub(super) expected_metric: Option<u64>,
    pub(super) expected_wall_recorded: bool,
}

pub(super) struct NestingTestCase {
    pub(super) description: &'static str,
    pub(super) inner_ns: u64,
    pub(super) outer_ns: u64,
    pub(super) expected_outer_ms: u64,
}

/// A clock that advances by `step` nanoseconds on every read.
pub(super) struct SteppingClock {
    pub(super) now: Cell<u64>,
    pub(super) step: u64,
}

impl ProcessClock for SteppingClock {
    type Error = ();

    fn process_time_ns(&self) -> Result<u64, ()> {
        let now: u64 = self.now.get() + self.step;
        self.now.set(now);
        Ok(now)
    }
}
