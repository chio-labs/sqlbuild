//! Native output-type recovery for failed models, with Python's revalidation in between.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyRef, PyResult, Python};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_analysis::semantic_checks::main::finish_type_recovery::finish_type_recovery;
use sqlbuild_analysis::semantic_checks::main::plan_type_recovery::plan_type_recovery;
use sqlbuild_analysis::semantic_checks::models::{
    DiagnosticOwner, LineageOutput, ModelBinding, RawBinding, RecoveryModel, TypeRecoveryPlan,
    TypeRecoveryRequest, TypeRecoveryStep,
};
use sqlbuild_analysis::semantic_checks::types::RevisedBinding;

use crate::bindings::_helpers::analysis_session::session::NativeModelAnalysisSession;
use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::semantic_checks::failures::{internal_error, semantic_error};
use crate::bindings::_helpers::semantic_checks::session_facts::session_model_facts;
use crate::bindings::models::ProjectCatalog;
use crate::bindings::types::CompilerDetach;

/// `(output_column, [(resource_name, column_name)])`.
pub(crate) type LineageInput = (String, Vec<(String, String)>);
/// `(name, query_sql, inferred names, reference names, lineage, bindings, raw bindings)`.
type ModelInput = (
    String,
    String,
    Option<Vec<String>>,
    Vec<String>,
    Option<Vec<LineageInput>>,
    Vec<(usize, String, String, bool)>,
    Vec<(usize, String, String, Option<i64>, Option<i64>)>,
);
/// `(dialect, models, [(id, code, is_model, resource_name)])`.
type RequestInput = (
    Option<String>,
    Vec<ModelInput>,
    Vec<(usize, String, bool, Option<String>)>,
);
/// `(kept [(diagnostic index, appended note)], model binding positions)`.
type OutcomeRow = (Vec<(usize, Option<String>)>, Vec<Vec<usize>>);

/// One planned type recovery, held between the native plan and Python's revalidation.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct SemanticTypeRecovery {
    request: TypeRecoveryRequest,
    step: TypeRecoveryStep,
}

#[pymethods]
impl SemanticTypeRecovery {
    /// `unchanged` or `planned`.
    #[getter]
    fn status(&self) -> &'static str {
        self.step.status()
    }

    /// Poisoned `(model, column)` outputs in Python's dict order.
    #[getter]
    fn poisoned(&self) -> Vec<(String, String)> {
        self.step
            .plan()
            .map(TypeRecoveryPlan::poisoned_outputs)
            .unwrap_or_default()
    }

    /// Model indexes Python revalidates with unknown poisoned types, in order.
    #[getter]
    fn revalidated(&self) -> Vec<usize> {
        self.step
            .plan()
            .map(TypeRecoveryPlan::revalidated_models)
            .unwrap_or_default()
    }

    /// Retained diagnostics and model binding positions; an internal failure raises.
    fn finish(&self, revised: Vec<Vec<RevisedBinding>>) -> PyResult<OutcomeRow> {
        let plan = self
            .step
            .plan()
            .ok_or_else(|| internal_error("finishing a type recovery that has no plan"))?;
        finish_type_recovery(&self.request, plan, &revised)
            .map(|outcome| (outcome.kept, outcome.model_bindings))
            .map_err(|reason| internal_error(&reason))
    }
}

/// Plan type recovery, reading names and lineage from `session` for models with no lineage.
#[pyfunction]
#[pyo3(signature = (catalog, request, session=None))]
fn plan_semantic_type_recovery(
    py: Python<'_>,
    catalog: PyRef<'_, ProjectCatalog>,
    request: RequestInput,
    session: Option<PyRef<'_, NativeModelAnalysisSession>>,
) -> PyResult<SemanticTypeRecovery> {
    let request = recovery_request(request, session.as_deref()).map_err(compiler_error)?;
    let catalog = &catalog.inner;
    let step = py
        .compiler_detach(|| Ok(plan_type_recovery(&request, catalog)))
        .map_err(compiler_error)?
        .map_err(|failure| semantic_error(py, &failure))?;
    Ok(SemanticTypeRecovery { request, step })
}

pub(crate) fn lineage_outputs(lineage: Vec<LineageInput>) -> Vec<LineageOutput> {
    lineage
        .into_iter()
        .map(|(output_column, upstream)| LineageOutput {
            output_column,
            upstream,
        })
        .collect()
}

fn recovery_request(
    (dialect, models, diagnostics): RequestInput,
    session: Option<&NativeModelAnalysisSession>,
) -> Result<TypeRecoveryRequest, String> {
    Ok(TypeRecoveryRequest {
        dialect,
        models: models
            .into_iter()
            .map(|model| recovery_model(model, session))
            .collect::<Result<_, _>>()?,
        diagnostics: diagnostics
            .into_iter()
            .map(|(id, code, is_model, resource_name)| DiagnosticOwner {
                id,
                code,
                is_model,
                resource_name,
            })
            .collect(),
    })
}

fn recovery_model(
    (name, query_sql, inferred_columns, references, lineage, bindings, raw_bindings): ModelInput,
    session: Option<&NativeModelAnalysisSession>,
) -> Result<RecoveryModel, String> {
    let (inferred_columns, lineage) = match lineage {
        Some(lineage) => (inferred_columns, lineage),
        None => {
            let facts = session_model_facts(session, &name)?;
            (facts.columns.clone(), facts.lineage.clone())
        }
    };
    Ok(RecoveryModel {
        name,
        query_sql,
        inferred_columns,
        references,
        lineage: lineage_outputs(lineage),
        bindings: bindings
            .into_iter()
            .map(|(id, code, message, is_error)| ModelBinding {
                id,
                code,
                message,
                is_error,
            })
            .collect(),
        raw_bindings: raw_bindings
            .into_iter()
            .map(|(id, code, message, start, end)| RawBinding {
                id,
                code,
                message,
                start,
                end,
            })
            .collect(),
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<SemanticTypeRecovery>()?;
    module.add_function(wrap_pyfunction!(plan_semantic_type_recovery, module)?)?;
    Ok(())
}
