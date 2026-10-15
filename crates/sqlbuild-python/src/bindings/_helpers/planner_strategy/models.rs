//! Extension-owned fixture analysis reuse, with pure state passed into analysis.

use pyo3::pyclass;
use sqlbuild_analysis::planner_fixtures::models::FixtureReadCache;

/// Per-extension cache replacing the Python fixture resolver's LRU.
#[pyclass]
#[derive(Debug, Default)]
pub(crate) struct FixtureReadCacheHost {
    pub(crate) cache: FixtureReadCache,
}
