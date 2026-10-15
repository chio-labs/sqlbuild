//! Register the native project discovery functions and classes.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::discovery::{
    declaration_files, declaration_records, description_inputs, guidance, header_declarations,
    header_values, hook_entries, imported_python_nodes, key_checks, locations, model_records,
    project_files, project_validation, python_function_files, python_hook_files,
    python_module_files, raised, scope_snapshot, snapshot, sql_test_records, yaml_entries,
    yaml_records,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    project_files::register(module)?;
    snapshot::register(module)?;
    scope_snapshot::register(module)?;
    declaration_files::register(module)?;
    declaration_records::register(module)?;
    python_function_files::register(module)?;
    python_hook_files::register(module)?;
    python_module_files::register(module)?;
    model_records::register(module)?;
    sql_test_records::register(module)?;
    yaml_records::register(module)?;
    raised::register(module)?;
    locations::register(module)?;
    header_declarations::register(module)?;
    key_checks::register(module)?;
    project_validation::register(module)?;
    yaml_entries::register(module)?;
    header_values::register(module)?;
    guidance::register(module)?;
    description_inputs::register(module)?;
    hook_entries::register(module)?;
    imported_python_nodes::register(module)?;
    Ok(())
}
