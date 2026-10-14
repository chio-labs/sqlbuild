//! Fixture analysis selection and diagnostic boundary conversions.

use std::collections::BTreeSet;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::{
    fixture_schema::fixture_schema, requires_analysis::requires_analysis,
    unknown_columns::unknown_columns,
};

use crate::bindings::_helpers::planner_strategy::fixture_values::{columns, diagnostic, label};

#[pyfunction]
#[pyo3(signature = (*, inferred_by_fixture, authoritative_columns))]
pub(crate) fn fixture_keys_requiring_analysis<'py>(
    inferred_by_fixture: &Bound<'py, PyDict>,
    authoritative_columns: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let mut selected: Vec<Bound<'py, PyAny>> = Vec::new();
    for (key, inferred) in inferred_by_fixture.iter() {
        let expected: Option<BTreeSet<String>> = authoritative_columns
            .get_item(&key)?
            .map(|names| names.extract())
            .transpose()?;
        if requires_analysis(&columns(&inferred, true)?, expected.as_ref()) {
            selected.push(key);
        }
    }
    PyFrozenSet::new(inferred_by_fixture.py(), selected)
}

#[pyfunction]
#[pyo3(signature = (*, inferred_by_fixture, relations))]
pub(crate) fn unknown_fixture_column_diagnostics<'py>(
    inferred_by_fixture: &Bound<'py, PyDict>,
    relations: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyTuple>> {
    let mut diagnostics = Vec::<Bound<'py, PyAny>>::new();
    for (key, inferred) in inferred_by_fixture.iter() {
        let Some(relation) = relations.get_item(&key)? else {
            continue;
        };
        let schema = fixture_schema(
            &columns(&relation.getattr("columns")?, false)?,
            relation.getattr("authoritative_names")?.extract()?,
        );
        if let Some(message) = unknown_columns(
            &label(&key)?,
            &columns(&inferred, true)?,
            schema.authoritative_names.as_ref(),
        ) {
            diagnostics.push(diagnostic(&key, &message)?);
        }
    }
    PyTuple::new(inferred_by_fixture.py(), diagnostics)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(fixture_keys_requiring_analysis, module)?)?;
    module.add_function(wrap_pyfunction!(
        unknown_fixture_column_diagnostics,
        module
    )?)
}
