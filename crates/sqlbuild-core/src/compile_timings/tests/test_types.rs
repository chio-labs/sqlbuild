use crate::compile_timings::models::CompileTimings;

pub(super) struct MillisecondsTestCase {
    pub(super) description: &'static str,
    pub(super) timings: CompileTimings,
    pub(super) expected_entries: Vec<(&'static str, u64)>,
}
