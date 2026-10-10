use crate::project_reuse::models::StoredOutput;

/// The stored report with freshly measured timings, or `None` when it cannot be spliced.
pub fn replay_stdout(output: &StoredOutput, timings: &[(String, i64)]) -> Option<String> {
    match output.timings_span {
        None => Some(output.stdout.clone()),
        Some(span) => crate::project_reuse::_helpers::timings::replace_compile_timings(
            &output.stdout,
            span,
            timings,
        ),
    }
}
