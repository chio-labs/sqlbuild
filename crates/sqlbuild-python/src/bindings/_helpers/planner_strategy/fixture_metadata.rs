//! Model fixture schema materialization at the Python boundary.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyTuple;
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::merge_metadata::merge_metadata;
use sqlbuild_analysis::planner_fixtures::models::FixtureColumn;
use sqlbuild_core::text::main::python_casefold::python_casefold;

use crate::bindings::_helpers::analysis::model_reads::{inferred_rows, star_flags};
use crate::bindings::_helpers::compiled_project::compiled_model_view::InferredRow;
use crate::bindings::_helpers::planner_strategy::fixture_values::{columns, metadata};

#[pyfunction]
#[pyo3(signature = (*, model))]
pub(crate) fn model_fixture_metadata<'py>(
    model: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = model.py();
    let inferred: Option<Vec<InferredRow>> = inferred_rows(model)?;
    let schema = model.getattr("schema_entry")?;
    let declared = if schema.is_none() {
        PyTuple::empty(py).into_any()
    } else {
        schema.getattr("columns")?
    };
    let mut inferred_columns: Vec<FixtureColumn> = Vec::new();
    for (name, sql_type, _) in inferred.iter().flatten() {
        inferred_columns.push(FixtureColumn {
            name: name.clone(),
            folded_name: python_casefold(name),
            sql_type: sql_type.clone(),
            nullable: None,
        });
    }
    let merged = merge_metadata(inferred_columns, columns(&declared, false)?);
    let authoritative = !star_flags(model)?.0
        && (model
            .getattr("config")?
            .getattr("values")?
            .call_method1("get", ("contract",))?
            .eq("enforced")?
            || inferred.is_some());
    metadata(py, &merged, authoritative)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(model_fixture_metadata, module)?)
}
