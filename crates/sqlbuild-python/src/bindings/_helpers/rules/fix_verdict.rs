//! Convert compiler fact views to native equality and diagnostic facts.

use std::collections::BTreeMap;

use pyo3::prelude::{Bound, IntoPyObject, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyList, PyListMethods, PyTuple};
use sqlbuild_rules::fix_verification::main::compare::compare;
use sqlbuild_rules::fix_verification::models::{DiagnosticComparison, ModelComparison};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const LINT_MODELS: &str = "sqlbuild.lint.models";

/// Compare compile facts using native decisions and the existing Python boundary models.
#[pyfunction]
#[pyo3(signature = (*, before, after, edited))]
pub(crate) fn fix_verdict<'py>(
    py: Python<'py>,
    before: &Bound<'py, PyAny>,
    after: &Bound<'py, PyAny>,
    edited: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let before_models = before.getattr("models")?.cast_into::<PyDict>()?;
    let after_models = after.getattr("models")?.cast_into::<PyDict>()?;
    let same_models = before_models
        .call_method0("keys")?
        .eq(after_models.call_method0("keys")?)?;
    let owners = PyList::empty(py);
    let indices = PyDict::new(py);
    let mut models: Vec<ModelComparison> = Vec::new();
    let mut diagnostics: Vec<DiagnosticComparison> = Vec::new();
    if same_models {
        let paths = before.getattr("model_paths")?;
        for (key, model) in before_models.iter() {
            let other = after_models
                .get_item(&key)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("model key"))?;
            let path = paths.get_item(&key)?;
            let owner = owner_index((&owners, &indices), &path)?;
            let columns = model.getattr("inferred_columns")?;
            let other_columns = other.getattr("inferred_columns")?;
            models.push(ModelComparison {
                owner,
                edited: edited.contains(&path)?,
                columns_known: !columns.is_none() && !other_columns.is_none(),
                columns_equal: columns.eq(&other_columns)?,
                dependencies_equal: model.getattr("deps")?.eq(other.getattr("deps")?)?,
                lineage_equal: lineage(&model)?.eq(lineage(&other)?)?,
            });
        }
        let previous = before.getattr("diagnostics")?.cast_into::<PyDict>()?;
        let current = after.getattr("diagnostics")?.cast_into::<PyDict>()?;
        let diagnostic_owners = PyDict::new(py);
        for (owner, _) in previous.iter().chain(current.iter()) {
            diagnostic_owners.set_item(owner, py.None())?;
        }
        for (path, _) in diagnostic_owners.iter() {
            diagnostics.push(DiagnosticComparison {
                owner: owner_index((&owners, &indices), &path)?,
                edited: edited.contains(&path)?,
                before: counts(previous.get_item(&path)?)?,
                after: counts(current.get_item(&path)?)?,
            });
        }
    }
    let result = compare(same_models, &models, &diagnostics);
    let failing = PyDict::new(py);
    for (owner, reason) in result.failing {
        failing.set_item(owners.get_item(owner)?, reason)?;
    }
    call_with(
        &imported(py, LINT_MODELS, "FixVerdict")?,
        &[
            ("failing", failing.into_any()),
            (
                "unattributed",
                result.unattributed.into_pyobject(py)?.to_owned().into_any(),
            ),
        ],
    )
}

fn owner_index(
    lookup: (&Bound<'_, PyList>, &Bound<'_, PyDict>),
    owner: &Bound<'_, PyAny>,
) -> PyResult<usize> {
    let (owners, indices) = lookup;
    if let Some(index) = indices.get_item(owner)? {
        return index.extract();
    }
    let index = owners.len();
    owners.append(owner)?;
    indices.set_item(owner, index)?;
    Ok(index)
}

fn lineage<'py>(model: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let value = model.getattr("fast_lineage_columns")?;
    if value.is_none() {
        Ok(value)
    } else {
        let items = value.try_iter()?.collect::<PyResult<Vec<_>>>()?;
        Ok(PyTuple::new(model.py(), items)?.into_any())
    }
}

fn counts(
    value: Option<Bound<'_, PyAny>>,
) -> PyResult<BTreeMap<(String, String, String, String), i64>> {
    value.map_or_else(|| Ok(BTreeMap::new()), |value| value.extract())
}
