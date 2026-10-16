//! Key rows and compiled expansions lint reads natively from compile inputs and compiled projects.

use std::collections::HashMap;
use std::path::PathBuf;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::PyStringMethods;

use crate::bindings::_helpers::compiled_project::compiled_model_view::NativeCompiledModel;
use crate::bindings::_helpers::compiled_project::model_input_view::{
    ExpansionRecord, ModelInputRecord, NativeModelInput, model_relation_key_row,
};
use crate::bindings::_helpers::compiled_project::project_view::NativeProjectView;
use crate::bindings::_helpers::rules::lint_pipeline::{CompiledExpansion, span_pass};
use crate::bindings::_helpers::rules::relation_keys::RelationKeyRow;

const FILE_PATH_ATTRIBUTE: &str = "file_path";

/// The declared key facts of a model input or compiled model.
pub(crate) fn model_key_row(model: &Bound<'_, PyAny>) -> PyResult<RelationKeyRow> {
    let py: Python<'_> = model.py();
    if let Ok(input) = model.downcast::<NativeModelInput>() {
        return input.get().read_with_owner(py, |owner, record| {
            model_relation_key_row(owner, record, py)
        });
    }
    if let Ok(compiled) = model.downcast::<NativeCompiledModel>() {
        return compiled.get().relation_key_row(py);
    }
    model.getattr("relation_key_row")?.extract()
}

/// The model file path of a native input record.
fn record_path(record: &ModelInputRecord, py: Python<'_>) -> PyResult<PathBuf> {
    record
        .model_file
        .bind(py)
        .getattr(FILE_PATH_ATTRIBUTE)?
        .extract()
}

/// An expansion record with the given passes.
fn expansion(
    expansion: &ExpansionRecord,
    passes: &[&Vec<(usize, usize, usize, usize)>],
    py: Python<'_>,
) -> PyResult<CompiledExpansion> {
    Ok(CompiledExpansion {
        authored_sql: expansion.authored_sql.bind(py).to_str()?.to_owned(),
        expanded_sql: expansion.expanded_sql.bind(py).to_str()?.to_owned(),
        passes: passes.iter().map(|rows| span_pass(rows)).collect(),
    })
}

/// A model input's whole compile expansion, variables included, keyed by its file path.
pub(crate) fn model_lint_expansion(
    model: &Bound<'_, PyAny>,
) -> PyResult<Option<(PathBuf, CompiledExpansion)>> {
    let py: Python<'_> = model.py();
    if let Ok(input) = model.downcast::<NativeModelInput>() {
        return input.get().read(py, |record, py| {
            let whole: &ExpansionRecord = &record.expansion;
            Ok(Some((
                record_path(record, py)?,
                expansion(
                    whole,
                    &[
                        &whole.interpolation_spans,
                        &whole.declaration_spans,
                        &whole.macro_spans,
                    ],
                    py,
                )?,
            )))
        });
    }
    let mut record: Bound<'_, PyAny> = model.getattr("lint_expansion")?;
    if !record.is_truthy()? {
        record = model.getattr("sql_expansion")?;
    }
    if record.is_none() {
        return Ok(None);
    }
    let path: PathBuf = model
        .getattr("model_file")?
        .getattr(FILE_PATH_ATTRIBUTE)?
        .extract()?;
    Ok(Some((path, CompiledExpansion::from_record(&record)?)))
}

/// A compiled project's authored expansions: models whose interpolation left the query unchanged.
pub(crate) fn project_sql_expansions(
    project: &Bound<'_, PyAny>,
) -> PyResult<HashMap<PathBuf, CompiledExpansion>> {
    let py: Python<'_> = project.py();
    let mut expansions: HashMap<PathBuf, CompiledExpansion> = HashMap::new();
    if let Ok(view) = project.downcast::<NativeProjectView>() {
        let owner = view.get().owner().bind(py).borrow();
        for record in owner.inputs() {
            let authored: &ExpansionRecord = &record.expansion;
            if authored.authored {
                expansions.insert(
                    record_path(record, py)?,
                    expansion(
                        authored,
                        &[&authored.declaration_spans, &authored.macro_spans],
                        py,
                    )?,
                );
            }
        }
        return Ok(expansions);
    }
    crate::bindings::_helpers::rules::run_lint::compiled_expansion_records(
        &project.getattr("sql_expansions")?,
    )
}
