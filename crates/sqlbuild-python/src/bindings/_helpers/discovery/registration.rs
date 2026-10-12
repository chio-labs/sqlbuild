//! Register the native project discovery functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::discovery::{
    declaration_files, declaration_records, globbing, header_declarations, key_checks,
    layout_groups, locations, model_records, project_files, project_validation, raised,
    sql_test_records, yaml_entries, yaml_records,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    project_files::register(module)?;
    declaration_files::register(module)?;
    declaration_records::register(module)?;
    layout_groups::register(module)?;
    model_records::register(module)?;
    sql_test_records::register(module)?;
    yaml_records::register(module)?;
    raised::register(module)?;
    locations::register(module)?;
    header_declarations::register(module)?;
    key_checks::register(module)?;
    globbing::register(module)?;
    project_validation::register(module)?;
    yaml_entries::register(module)?;
    Ok(())
}
