use pyo3::prelude::{Bound, PyAny};
use pyo3::types::PyDict;

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
