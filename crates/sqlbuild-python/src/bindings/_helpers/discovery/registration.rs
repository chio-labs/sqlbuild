//! Register the native project discovery functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::discovery::{
    declaration_files, globbing, header_declarations, key_checks, locations, project_files,
    sql_test_blocks,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    project_files::register(module)?;
    declaration_files::register(module)?;
    locations::register(module)?;
    sql_test_blocks::register(module)?;
    header_declarations::register(module)?;
    key_checks::register(module)?;
    globbing::register(module)?;
    Ok(())
}
