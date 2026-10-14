//! Migration identity binding with unchanged metadata and hash format.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyFrozenSet};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_migrations::main::{migration_fingerprint, migration_ref_names};
use std::collections::BTreeMap;

/// Hash normalized SQL and non-storage metadata through rename identities.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_migration_fingerprint(
    py: Python<'_>,
    options: Option<Bound<'_, PyDict>>,
) -> PyResult<Option<String>> {
    let arguments = KeywordArguments::read(
        py,
        "build_migration_fingerprint",
        options,
        (
            &["query_sql", "metadata_json", "ref_identities", "dialect"],
            &[],
        ),
    )?;
    let mut identities: BTreeMap<String, String> = BTreeMap::new();
    for item in arguments
        .value("ref_identities")?
        .call_method0("items")?
        .try_iter()?
    {
        let (key, value): (String, String) = item?.extract()?;
        identities.insert(key, value);
    }
    let sql: String = arguments.value("query_sql")?.extract()?;
    let metadata: String = arguments.value("metadata_json")?.extract()?;
    let dialect: Option<String> = arguments.value("dialect")?.extract()?;
    migration_fingerprint::migration_fingerprint(
        &sql,
        &metadata,
        &identities,
        dialect
            .as_deref()
            .filter(|value| !value.is_empty())
            .unwrap_or("generic"),
    )
    .map_err(PyValueError::new_err)
}

/// Every name whose rename identity can change the migration fingerprint.
#[pyfunction]
#[pyo3(signature = (*, query_sql, metadata_json))]
fn migration_fingerprint_ref_names<'py>(
    py: Python<'py>,
    query_sql: &str,
    metadata_json: &str,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    PyFrozenSet::new(
        py,
        migration_ref_names::migration_ref_names(query_sql, metadata_json)
            .map_err(PyValueError::new_err)?,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_migration_fingerprint, module)?)?;
    module.add_function(wrap_pyfunction!(migration_fingerprint_ref_names, module)?)
}
