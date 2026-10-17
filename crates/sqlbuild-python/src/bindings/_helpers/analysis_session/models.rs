//! Native state kept by the analysis-session bindings.

use pyo3::pyclass;

/// Fixture column inferences computed since the last reset.
#[pyclass]
#[derive(Debug, Default)]
pub(crate) struct FixtureInferenceCount {
    pub(crate) computed: u64,
}
