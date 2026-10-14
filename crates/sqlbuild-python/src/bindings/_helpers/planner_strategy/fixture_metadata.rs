//! Model fixture schema materialization at the Python boundary.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult};
use pyo3::types::PyTuple;
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_fixtures::main::merge_metadata::merge_metadata;

use crate::bindings::_helpers::planner_strategy::fixture_values::{columns, metadata};

#[pyfunction]
#[pyo3(signature = (*, model))]
fn model_fixture_metadata<'py>(model: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py = model.py();
    let inferred = model.getattr("inferred_columns")?;
    let schema = model.getattr("schema_entry")?;
    let declared = if schema.is_none() {
        PyTuple::empty(py).into_any()
    } else {
        schema.getattr("columns")?
    };
    let inferred_columns = if inferred.is_none() {
        Vec::new()
    } else {
        columns(&inferred, true)?
    };
    let merged = merge_metadata(inferred_columns, columns(&declared, false)?);
    let authoritative = !model.getattr("fast_lineage_has_star")?.is_truthy()?
        && (model
            .getattr("config")?
            .getattr("values")?
            .call_method1("get", ("contract",))?
            .eq("enforced")?
            || !inferred.is_none());
    metadata(py, &merged, authoritative)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(model_fixture_metadata, module)?)
}
