//! Every model's native facts and the project's resource facts, from the native stages.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyListMethods, PyTuple};

use crate::bindings::_helpers::compile_driver::assembly_analysis::AnalysisContext;
use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::project_assembly::models::{NativeModelFacts, NativeProjectFacts};
use crate::bindings::_helpers::project_assembly::native_resources::assemble_native_project_resources;
use crate::bindings::_helpers::project_assembly::syntax_checks::model_syntax_checks;
use crate::bindings::_helpers::project_assembly::syntax_checks::standalone_pivot_models;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::IntoPyObjectExt;

/// `NativeProjectFacts` of `inputs`: resources, syntax validity, deps and standalone pivot proofs.
pub(crate) fn native_project_facts<'py>(
    inputs: &Bound<'py, PyAny>,
    context: &AnalysisContext<'py>,
    names: &Bound<'py, PyAny>,
    session: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let model_inputs: Bound<'py, PyAny> = inputs.getattr("model_inputs")?;
    let dialect: Bound<'py, PyAny> = context.profile.getattr("sql_analysis_dialect")?;
    let (succeeded, positions): (Bound<'py, PyAny>, Bound<'py, PyAny>) = match &context.analyses {
        Some(analyses) => (
            analyses.succeeded.clone().into_any(),
            analyses.positions.clone().into_any(),
        ),
        None => (
            PyFrozenSet::empty(py)?.into_any(),
            PyDict::new(py).into_any(),
        ),
    };
    let syntax_checks: Bound<'py, PyAny> =
        model_syntax_checks(&model_inputs.clone(), &names.clone(), &succeeded)
            .and_then(|value| value.into_bound_py_any(py))?;
    let resources: Bound<'py, PyAny> = assemble_native_project_resources(
        &inputs.clone(),
        dialect.clone().extract()?,
        &syntax_checks,
    )
    .and_then(|value| value.into_bound_py_any(py))?;
    let proofs: Bound<'py, PyDict> = pivot_proofs(
        &standalone_pivot_models(&model_inputs.clone(), &positions)
            .and_then(|value| value.into_bound_py_any(py))?
            .cast_into::<PyDict>()?,
        context,
        session,
    )?;
    let deps: Bound<'py, PyAny> = resources.getattr("model_deps")?;
    let syntax_valid: Bound<'py, PyAny> = resources.getattr("model_syntax_valid")?;
    let mut models: Vec<Bound<'py, PyAny>> = Vec::new();
    for index in 0..model_inputs.len()? {
        let proof: Bound<'py, PyAny> = match proofs.get_item(index)? {
            Some(proof) => proof,
            None => py.None().into_bound(py),
        };
        models.push(
            Bound::new(
                py,
                NativeModelFacts {
                    deps: deps.get_item(index)?.unbind(),
                    dynamic_contract: proof.unbind(),
                    syntax_valid: syntax_valid.get_item(index)?.unbind(),
                },
            )?
            .into_any(),
        );
    }
    Ok(Bound::new(
        py,
        NativeProjectFacts {
            models: PyTuple::new(py, models)?.into_any().unbind(),
            resources: resources.unbind(),
        },
    )?
    .into_any())
}

/// Each standalone pivot model's dynamic contract proof, by model position.
fn pivot_proofs<'py>(
    pivots: &Bound<'py, PyDict>,
    context: &AnalysisContext<'py>,
    session: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = pivots.py();
    let tables: Bound<'py, PyAny> = call_with(
        &registry::class(py, RecordId::NativePivotTables)?,
        &[
            ("dialect", context.profile.getattr("sql_analysis_dialect")?),
            ("column_types_by_table", context.column_types.clone()),
            (
                "authoritative_column_types_by_table",
                context.complete_schemas.clone(),
            ),
            ("column_nullability_by_table", context.nullability.clone()),
            (
                "dynamic_families_by_table",
                context.dynamic_families.clone(),
            ),
        ],
    )?;
    let proven: Vec<Bound<'py, PyAny>> = call_with(
        &registry::native(py, NativeAttr::ProveNativeDynamicContracts)?,
        &[
            ("session", session.clone()),
            ("tables", tables),
            ("models", PyTuple::new(py, pivots.values())?.into_any()),
        ],
    )?
    .try_iter()?
    .collect::<PyResult<_>>()?;
    if proven.len() != pivots.len() {
        return Err(PyValueError::new_err(
            "native pivot proofs do not match the standalone pivot models",
        ));
    }
    let proofs: Bound<'py, PyDict> = PyDict::new(py);
    for (index, proof) in pivots.keys().iter().zip(proven) {
        proofs.set_item(index, proof)?;
    }
    Ok(proofs)
}
