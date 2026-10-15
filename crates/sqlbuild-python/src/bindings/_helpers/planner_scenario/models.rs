//! Borrowed Python callback boundaries for scenario SQL assembly.

use pyo3::prelude::{Bound, PyAny};

#[derive(Debug)]
pub(crate) struct SqlContext<'py> {
    pub adapter: Bound<'py, PyAny>,
    pub relations: Bound<'py, PyAny>,
    pub syntax: Bound<'py, PyAny>,
    pub label: String,
}
