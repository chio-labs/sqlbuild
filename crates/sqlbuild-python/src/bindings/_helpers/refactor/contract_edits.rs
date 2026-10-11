//! Contract adoption's MODEL header and YAML source edits, computed natively.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_refactor::refactoring::errors::{RefactorError, RefactorErrorKind};
use sqlbuild_refactor::refactoring::main::edit_model_contract::edit_model_contract;
use sqlbuild_refactor::refactoring::main::edit_source_contract::edit_source_contract;
use sqlbuild_refactor::refactoring::models::{
    ContractEdit, ContractModelColumn, ContractModelRequest, ContractSourceRequest,
};
use sqlbuild_refactor::refactoring::types::PhysicalColumn;

use crate::bindings::_helpers::boundary::panics::compiler_guard;

/// `(edited contents, ownership conflict, ContractAdoptionError message)`.
type EditRow = (Option<String>, Option<String>, Option<String>);
type ModelColumnRow = (String, Option<String>, Option<String>);
type ModelRow = (
    String,
    String,
    bool,
    Vec<ModelColumnRow>,
    Vec<Option<String>>,
    Vec<PhysicalColumn>,
    bool,
);
type SourceRow = (
    String,
    String,
    String,
    Vec<(String, Option<String>)>,
    Vec<PhysicalColumn>,
    bool,
);

fn edit_row(result: Result<ContractEdit, RefactorError>) -> PyResult<EditRow> {
    match result {
        Ok(ContractEdit::Edited(contents)) => Ok((Some(contents), None, None)),
        Ok(ContractEdit::Conflict(conflict)) => Ok((None, Some(conflict), None)),
        Err(error) if error.kind == RefactorErrorKind::Edit => {
            Ok((None, None, Some(error.message)))
        }
        Err(error) => Err(PyValueError::new_err(error.message)),
    }
}

/// Python's `edit_model` over the model facts a compiled view holds.
#[pyfunction]
fn contract_model_edit(row: ModelRow) -> PyResult<EditRow> {
    let (contents, relative_path, shared_schema, columns, dynamic_patterns, physical, overwrite) =
        row;
    let request = ContractModelRequest {
        contents,
        relative_path,
        shared_schema,
        columns: columns
            .into_iter()
            .map(|(name, declared_type, location_path)| ContractModelColumn {
                name,
                declared_type,
                location_path,
            })
            .collect(),
        dynamic_patterns,
        physical_columns: physical,
        overwrite,
    };
    compiler_guard(|| edit_row(edit_model_contract(&request)))
}

/// Python's `edit_source` over the source facts a compiled view holds.
#[pyfunction]
fn contract_source_edit(row: SourceRow) -> PyResult<EditRow> {
    let (contents, discovered_contents, name, columns, physical, overwrite) = row;
    let request = ContractSourceRequest {
        contents,
        discovered_contents,
        name,
        columns,
        physical_columns: physical,
        overwrite,
    };
    compiler_guard(|| edit_row(Ok(edit_source_contract(&request))))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(contract_model_edit, module)?)?;
    module.add_function(wrap_pyfunction!(contract_source_edit, module)?)?;
    Ok(())
}
