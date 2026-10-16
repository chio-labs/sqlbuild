use pyo3::prelude::{Bound, PyAny};
use pyo3::types::PyDict;

#[derive(Debug)]
pub(crate) struct OldNamePlanner<'py> {
    pub runtime: Bound<'py, PyAny>,
    pub models: Vec<Bound<'py, PyAny>>,
    pub histories: Vec<Bound<'py, PyAny>>,
    pub views: Bound<'py, PyAny>,
    pub columns: Bound<'py, PyAny>,
    pub retention: Bound<'py, PyAny>,
    pub now: Bound<'py, PyAny>,
}

#[derive(Debug)]
pub(crate) struct ColumnCandidate<'py> {
    pub model: Bound<'py, PyAny>,
    pub warehouse: Bound<'py, PyDict>,
    pub declared: Bound<'py, PyDict>,
    pub fingerprint: Bound<'py, PyAny>,
    pub previous: Bound<'py, PyAny>,
    pub current: Bound<'py, PyAny>,
}
#[derive(Debug)]
pub(crate) struct CheckedColumns<'py> {
    pub entries: Vec<Bound<'py, PyAny>>,
    pub warnings: Vec<Bound<'py, PyAny>>,
}

/// The planning-phase inputs every migration planner reads.
#[derive(Debug)]
pub(crate) struct MigrationPhase<'py> {
    pub(crate) runtime: Bound<'py, PyAny>,
    pub(crate) scope: Bound<'py, PyAny>,
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) overrides: Bound<'py, PyAny>,
    pub(crate) deferral: Bound<'py, PyAny>,
}

/// The column migration planning inputs beyond the phase.
#[derive(Debug)]
pub(crate) struct ColumnMigrationInputs<'py> {
    pub(crate) full_refresh_model_names: Bound<'py, PyAny>,
    pub(crate) physical_relations: Bound<'py, PyAny>,
    pub(crate) source_columns: Bound<'py, PyAny>,
}

/// The snapshot after model migrations overlay it, with the planned entries and their warnings.
#[derive(Debug)]
pub(crate) struct ModelMigrationPlanning<'py> {
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) entries: Vec<Bound<'py, PyAny>>,
    pub(crate) warnings: Vec<Bound<'py, PyAny>>,
}

/// The snapshot after column renames overlay it, with the planned entries, rename hints and warnings.
#[derive(Debug)]
pub(crate) struct ColumnMigrationPlanning<'py> {
    pub(crate) snapshot: Bound<'py, PyAny>,
    pub(crate) entries: Vec<Bound<'py, PyAny>>,
    pub(crate) hints: Vec<Bound<'py, PyAny>>,
    pub(crate) warnings: Vec<Bound<'py, PyAny>>,
}

/// The old-name view steps, the recorded live views and the warnings they raise.
#[derive(Debug)]
pub(crate) struct OldNameViewPlanning<'py> {
    pub(crate) entries: Bound<'py, PyAny>,
    pub(crate) views: Bound<'py, PyAny>,
    pub(crate) warnings: Vec<Bound<'py, PyAny>>,
}
