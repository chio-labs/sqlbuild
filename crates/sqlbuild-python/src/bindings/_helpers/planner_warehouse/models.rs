//! Warehouse planning state shared across planner runs.

use std::collections::BTreeSet;

use pyo3::pyclass;

/// Migration fingerprints computed since the last reset, for work-count tests.
#[pyclass]
#[derive(Debug, Default)]
pub(crate) struct FingerprintWork {
    pub(crate) computations: u64,
    pub(crate) distinct: BTreeSet<u64>,
}
