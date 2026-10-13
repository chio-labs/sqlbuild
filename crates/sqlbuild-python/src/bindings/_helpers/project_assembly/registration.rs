//! Register the native project assembly functions.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::project_assembly::{
    declared_relations, resources, syntax_checks, syntax_validation,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    declared_relations::register(module)?;
    syntax_validation::register(module)?;
    syntax_checks::register(module)?;
    resources::register(module)
}
