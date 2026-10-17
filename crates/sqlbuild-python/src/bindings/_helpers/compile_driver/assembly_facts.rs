//! Every model's native facts and the project's resource facts, from the native stages.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyListMethods, PyTuple, PyTupleMethods};

use crate::bindings::_helpers::analysis_session::stage_functions::dynamic_contract_proofs;
use crate::bindings::_helpers::compile_driver::assembly_analysis::AnalysisContext;
use crate::bindings::_helpers::compile_driver::stage_work::{
    PIVOT_PROOFS, SESSION_PIVOT_PROOFS, count_stage,
};
use crate::bindings::_helpers::project_assembly::models::{NativeModelFacts, NativeProjectFacts};
use crate::bindings::_helpers::project_assembly::native_resources::assemble_native_project_resources;
use crate::bindings::_helpers::project_assembly::syntax_checks::model_syntax_checks;
use crate::bindings::_helpers::project_assembly::syntax_checks::standalone_pivot_models;
use crate::bindings::_helpers::records::construct::new_record_with;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::IntoPyObjectExt;

/// `NativeProjectFacts` of `inputs`: resources, syntax validity, deps and standalone pivot proofs.
pub(crate) fn native_project_facts<'py>(
    inputs: &Bound<'py, PyAny>,
    context: &AnalysisContext<'py>,
    names: &Bound<'py, PyAny>,
    session: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let model_inputs: Bound<'py, PyAny> = native_field(inputs, "model_inputs")?;
    let dialect: Bound<'py, PyAny> = native_field(&context.profile, "sql_analysis_dialect")?;
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
    let deps: Bound<'py, PyAny> = native_field(&resources, "model_deps")?;
    let syntax_valid: Bound<'py, PyAny> = native_field(&resources, "model_syntax_valid")?;
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

/// The declared relation facts standalone pivot proofs read.
pub(crate) fn pivot_tables<'py>(context: &AnalysisContext<'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.profile.py();
    new_record_with(
        py,
        RecordId::NativePivotTables,
        &[
            (
                "dialect",
                native_field(&context.profile, "sql_analysis_dialect")?,
            ),
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
    )
}

/// Each standalone pivot model's dynamic contract proof, by model position.
fn pivot_proofs<'py>(
    pivots: &Bound<'py, PyDict>,
    context: &AnalysisContext<'py>,
    session: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let tables: Bound<'py, PyAny> = pivot_tables(context)?;
    let py: Python<'py> = pivots.py();
    let proven: Vec<Bound<'py, PyAny>> = dynamic_contract_proofs(
        session,
        &tables,
        &PyTuple::new(py, pivots.values())?.into_any(),
    )?
    .iter()
    .collect();
    count_stage(py, PIVOT_PROOFS, proven.len() as u64)?;
    if !session.is_none() {
        let session_proofs: usize = proven.iter().filter(|proof| !proof.is_none()).count();
        count_stage(py, SESSION_PIVOT_PROOFS, session_proofs as u64)?;
    }
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
