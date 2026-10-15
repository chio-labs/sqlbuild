//! Register the native build, audit and test progress reporters, the build footer and the transient status.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::build_progress::{
    audit_progress, build_callbacks, footer, nested_progress, terminal, transient_lines,
    transient_status,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    audit_progress::register(module)?;
    build_callbacks::register(module)?;
    footer::register(module)?;
    nested_progress::register(module)?;
    terminal::register(module)?;
    transient_lines::register(module)?;
    transient_status::register(module)
}
