//! Fingerprint table SQL: DDL, the latest-row read, its node filter, and batched inserts.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::PyTuple;
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::fingerprint_storage::errors::FingerprintStorageError;
use sqlbuild_analysis::fingerprint_storage::main::create_table_sql::create_table_sql;
use sqlbuild_analysis::fingerprint_storage::main::insert_batch_lengths::insert_batch_lengths;
use sqlbuild_analysis::fingerprint_storage::main::insert_sql::insert_sql;
use sqlbuild_analysis::fingerprint_storage::main::read_latest_sql::read_latest_sql;
use sqlbuild_analysis::fingerprint_storage::main::relevant_read_sql::relevant_read_sql;
use sqlbuild_analysis::fingerprint_storage::models::{RelevantRead, StoredFingerprint};

use crate::bindings::_helpers::fingerprints::latest_rows::fingerprint_input_error;

/// `CREATE TABLE IF NOT EXISTS` for the fingerprint table, given `(string_type, timestamp_type)`.
#[pyfunction]
fn fingerprint_create_table_sql(qualified_name: &str, column_types: (String, String)) -> String {
    create_table_sql(qualified_name, &column_types.0, &column_types.1)
}

/// The windowed latest-row read of the fingerprint table.
#[pyfunction]
fn fingerprint_read_latest_sql(qualified_name: &str) -> String {
    read_latest_sql(qualified_name)
}

/// The latest-row read narrowed to the relevant nodes, or `None` when nothing can match.
#[pyfunction]
#[pyo3(signature = (read_sql, node_names, filtered_node_types))]
fn fingerprint_relevant_read_sql(
    read_sql: &str,
    node_names: Option<Vec<String>>,
    filtered_node_types: Vec<String>,
) -> Option<String> {
    match relevant_read_sql(read_sql, node_names.as_deref(), &filtered_node_types) {
        RelevantRead::Sql(sql) => Some(sql),
        RelevantRead::Empty => None,
    }
}

/// One `INSERT` of a single fingerprint.
#[pyfunction]
fn fingerprint_insert_sql(
    py: Python<'_>,
    qualified_name: &str,
    fingerprint: &Bound<'_, PyAny>,
) -> PyResult<String> {
    insert_sql(qualified_name, &[stored_fingerprint(fingerprint)?])
        .map_err(|error| storage_error(py, error))
}

/// `(batch, insert_sql)` per bounded batch, given `(batch_size, batch_max_bytes)`.
#[pyfunction]
fn fingerprint_insert_batches<'py>(
    py: Python<'py>,
    qualified_name: &str,
    fingerprints: Vec<Bound<'py, PyAny>>,
    limits: (i64, i64),
) -> PyResult<Vec<(Bound<'py, PyTuple>, String)>> {
    let stored: Vec<StoredFingerprint> = fingerprints
        .iter()
        .map(stored_fingerprint)
        .collect::<PyResult<_>>()?;
    let lengths: Vec<usize> = insert_batch_lengths(qualified_name, &stored, limits.0, limits.1)
        .map_err(|error| storage_error(py, error))?;
    let mut batches: Vec<(Bound<'py, PyTuple>, String)> = Vec::with_capacity(lengths.len());
    let mut start: usize = 0;
    for length in lengths {
        let end: usize = start + length;
        let sql: String = insert_sql(qualified_name, &stored[start..end])
            .map_err(|error| storage_error(py, error))?;
        batches.push((PyTuple::new(py, &fingerprints[start..end])?, sql));
        start = end;
    }
    Ok(batches)
}

fn stored_fingerprint(fingerprint: &Bound<'_, PyAny>) -> PyResult<StoredFingerprint> {
    Ok(StoredFingerprint {
        node_type: fingerprint.getattr("node_type")?.extract()?,
        node_name: fingerprint.getattr("node_name")?.extract()?,
        target_database: fingerprint.getattr("target_database")?.extract()?,
        target_schema: fingerprint.getattr("target_schema")?.extract()?,
        target_name: fingerprint.getattr("target_name")?.extract()?,
        run_id: formatted(fingerprint, "run_id")?,
        definition_hash: formatted(fingerprint, "definition_hash")?,
        version_hash: formatted(fingerprint, "version_hash")?,
        schema_fingerprint: formatted(fingerprint, "schema_fingerprint")?,
        definition: fingerprint.getattr("definition")?.extract()?,
        metadata_json: fingerprint.getattr("metadata_json")?.extract()?,
        ts: fingerprint
            .getattr("ts")?
            .call_method0("isoformat")?
            .extract()?,
    })
}

fn formatted(fingerprint: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    fingerprint.getattr(name)?.str()?.extract()
}

fn storage_error(py: Python<'_>, error: FingerprintStorageError) -> PyErr {
    fingerprint_input_error(py, &error.to_string())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(fingerprint_create_table_sql, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint_read_latest_sql, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint_relevant_read_sql, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint_insert_sql, module)?)?;
    module.add_function(wrap_pyfunction!(fingerprint_insert_batches, module)?)?;
    Ok(())
}
