//! `run_bounds_problem`: the selection, concurrency and worker rules of a run.

/// The rule a run's selection, concurrency and worker counts break.
#[must_use]
pub fn run_bounds_problem(
    selected_count: i128,
    configured_concurrency: i128,
    worker_count: i128,
) -> Option<&'static str> {
    if selected_count < 0 {
        return Some("selected_count must be nonnegative");
    }
    if configured_concurrency < 1 {
        return Some("configured_concurrency must be positive");
    }
    (worker_count != configured_concurrency.min(selected_count))
        .then_some("worker_count must equal min(configured_concurrency, selected_count)")
}
