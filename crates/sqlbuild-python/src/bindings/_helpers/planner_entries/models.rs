//! Typed requests of plan entry construction.

use pyo3::prelude::{Bound, PyAny};

/// What resolving relation locations and source metadata for one scope reads.
#[derive(Debug)]
pub(crate) struct RelationsRequest<'py> {
    pub(crate) project: Bound<'py, PyAny>,
    pub(crate) adapter: Bound<'py, PyAny>,
    pub(crate) connection: Bound<'py, PyAny>,
    pub(crate) scope: Bound<'py, PyAny>,
    pub(crate) deferral: Bound<'py, PyAny>,
    pub(crate) project_config: Bound<'py, PyAny>,
    pub(crate) local_config: Bound<'py, PyAny>,
    pub(crate) known_source_columns: Bound<'py, PyAny>,
    pub(crate) relation_keys: Bound<'py, PyAny>,
}

/// What building model plan entries for one execution scope reads.
#[derive(Debug)]
pub(crate) struct PlanEntriesRequest<'py> {
    pub(crate) project: Bound<'py, PyAny>,
    pub(crate) adapter: Bound<'py, PyAny>,
    pub(crate) scope: Bound<'py, PyAny>,
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) relations: Bound<'py, PyAny>,
    pub(crate) resolved_models: Bound<'py, PyAny>,
    pub(crate) cursor_overrides: Bound<'py, PyAny>,
    pub(crate) full_refresh: bool,
    pub(crate) build_inputs: Bound<'py, PyAny>,
}

/// What assembling the plan output's fields reads.
#[derive(Debug)]
pub(crate) struct PlanOutputInputs<'py> {
    pub(crate) project: Bound<'py, PyAny>,
    pub(crate) adapter: Bound<'py, PyAny>,
    pub(crate) scope: Bound<'py, PyAny>,
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) relations: Bound<'py, PyAny>,
    pub(crate) changes: Bound<'py, PyAny>,
    pub(crate) model_entries: Vec<Bound<'py, PyAny>>,
    pub(crate) model_warnings: Vec<Bound<'py, PyAny>>,
    pub(crate) reload_sources: Bound<'py, PyAny>,
    pub(crate) extras: Bound<'py, PyAny>,
}
