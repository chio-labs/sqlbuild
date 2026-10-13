//! Native output-type recovery for failed models, revalidating planned models in Python.

use std::collections::HashSet;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyList, PyString, PyTuple};
use sqlbuild_analysis::semantic_checks::main::finish_type_recovery::finish_type_recovery;
use sqlbuild_analysis::semantic_checks::main::plan_type_recovery::plan_type_recovery;
use sqlbuild_analysis::semantic_checks::models::{
    DiagnosticOwner, LineageOutput, ModelBinding, RawBinding, RecoveryModel, TypeRecoveryRequest,
};
use sqlbuild_analysis::semantic_checks::types::RevisedBinding;
use sqlbuild_analysis::semantic_validation::models as validation;

use crate::bindings::_helpers::analysis_session::session::NativeModelAnalysisSession;
use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::semantic_checks::failures::{internal_error, semantic_error};
use crate::bindings::_helpers::semantic_checks::session_facts::{
    column_names, session_model_facts,
};
use crate::bindings::_helpers::semantic_checks::stage_objects::StageClasses;
use crate::bindings::types::CompilerDetach;

const UNCHANGED: &str = "unchanged";
const UNKNOWN_RECOVERED_TYPE: &str = "UNKNOWN";

/// `(output_column, [(resource_name, column_name)])`.
pub(crate) type LineageInput = (String, Vec<(String, String)>);

/// The analysis state every semantic completion step shares.
pub(crate) struct StageShared<'a> {
    pub(crate) catalog: &'a validation::ProjectCatalog,
    pub(crate) session: Option<&'a NativeModelAnalysisSession>,
    /// Models whose output names and lineage the finished session supplies.
    pub(crate) session_models: HashSet<String>,
}

/// The project with recovered output types; unchanged when no model has a blocking binding.
pub(crate) fn recovered_types<'py>(
    classes: &StageClasses<'py>,
    project: &Bound<'py, PyAny>,
    binding_results: &Bound<'py, PyAny>,
    shared: &StageShared<'_>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = classes.py();
    let models: Vec<Bound<'py, PyAny>> = items(&project.getattr("models")?)?;
    if !blocking_binding_found(&models)? {
        return Ok(project.clone());
    }
    let ids: Bound<'py, PyDict> = diagnostic_ids(project, &models)?;
    let raw_ids: Bound<'py, PyDict> = PyDict::new(py);
    for rows in binding_results.call_method0("values")?.try_iter()? {
        for row in rows?.try_iter()? {
            let row: Bound<'py, PyAny> = row?;
            if !raw_ids.contains(&row)? {
                raw_ids.set_item(&row, raw_ids.len())?;
            }
        }
    }
    let diagnostics: Vec<Bound<'py, PyAny>> = items(&project.getattr("diagnostics")?)?;
    let mut owners: Vec<DiagnosticOwner> = Vec::with_capacity(diagnostics.len());
    for item in &diagnostics {
        owners.push(DiagnosticOwner {
            id: id_of(&ids, item)?,
            code: item.getattr("code")?.extract()?,
            is_model: item.getattr("resource_type")?.eq(&classes.model_resource)?,
            resource_name: item.getattr("resource_name")?.extract()?,
        });
    }
    let mut recovery_models: Vec<RecoveryModel> = Vec::with_capacity(models.len());
    for model in &models {
        recovery_models.push(recovery_model(
            model,
            binding_results,
            (&ids, &raw_ids),
            shared,
        )?);
    }
    let request = TypeRecoveryRequest {
        dialect: project.getattr("sql_analysis_dialect")?.extract()?,
        models: recovery_models,
        diagnostics: owners,
    };
    let step = py
        .compiler_detach(|| Ok(plan_type_recovery(&request, shared.catalog)))
        .map_err(compiler_error)?
        .map_err(|failure| semantic_error(py, &failure))?;
    if step.status() == UNCHANGED {
        return Ok(project.clone());
    }
    let plan = step
        .plan()
        .ok_or_else(|| internal_error("finishing a type recovery that has no plan"))?;
    let poisoned: Vec<(String, String)> = plan.poisoned_outputs();
    let revised: Vec<Vec<RevisedBinding>> =
        revalidated(classes, project, &plan.revalidated_models(), &poisoned)?;
    let outcome =
        finish_type_recovery(&request, plan, &revised).map_err(|reason| internal_error(&reason))?;
    let mut kept: Vec<Bound<'py, PyAny>> = Vec::with_capacity(outcome.kept.len());
    for (index, note) in outcome.kept {
        let original: &Bound<'py, PyAny> = &diagnostics[index];
        let mut notes: Vec<Bound<'py, PyAny>> = items(&original.getattr("notes")?)?;
        if let Some(note) = note {
            notes.push(PyString::new(py, &note).into_any());
        }
        kept.push(classes.replaced(original, &[("notes", &PyTuple::new(py, notes)?.into_any())])?);
    }
    let poisoned_outputs: Bound<'py, PyAny> = PyFrozenSet::new(py, &poisoned)?.into_any();
    let mut recovered: Vec<Bound<'py, PyAny>> = Vec::with_capacity(models.len());
    for (model, positions) in models.iter().zip(outcome.model_bindings) {
        let selected: Vec<Bound<'py, PyAny>> = positions
            .into_iter()
            .map(|position| kept[position].clone())
            .collect();
        recovered.push(classes.call(
            &classes.with_type_recovery,
            &[
                ("model", model),
                ("diagnostics", &PyTuple::new(py, selected)?.into_any()),
                ("poisoned", &poisoned_outputs),
            ],
        )?);
    }
    classes.project_with(
        project,
        &[
            ("models", &PyTuple::new(py, recovered)?.into_any()),
            ("diagnostics", &PyTuple::new(py, kept)?.into_any()),
        ],
    )
}

/// Every item of a Python iterable.
pub(crate) fn items<'py>(value: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    value.try_iter()?.collect()
}

/// One id per distinct diagnostic value, project diagnostics first, as Python's dicts see them.
pub(crate) fn diagnostic_ids<'py>(
    project: &Bound<'py, PyAny>,
    models: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyDict>> {
    let ids: Bound<'py, PyDict> = PyDict::new(project.py());
    for item in project.getattr("diagnostics")?.try_iter()? {
        let item: Bound<'py, PyAny> = item?;
        if !ids.contains(&item)? {
            ids.set_item(&item, ids.len())?;
        }
    }
    for model in models {
        for item in model.getattr("binding_diagnostics")?.try_iter()? {
            let item: Bound<'py, PyAny> = item?;
            if !ids.contains(&item)? {
                ids.set_item(&item, ids.len())?;
            }
        }
    }
    Ok(ids)
}

pub(crate) fn id_of(ids: &Bound<'_, PyDict>, item: &Bound<'_, PyAny>) -> PyResult<usize> {
    ids.as_any().get_item(item)?.extract()
}

/// Each output column with the `(resource, column)` pairs it reads.
pub(crate) fn lineage_payload(model: &Bound<'_, PyAny>) -> PyResult<Vec<LineageInput>> {
    let columns: Bound<'_, PyAny> = model.getattr("fast_lineage_columns")?;
    if !columns.is_truthy()? {
        return Ok(Vec::new());
    }
    let mut lineage: Vec<LineageInput> = Vec::new();
    for output in columns.try_iter()? {
        let output: Bound<'_, PyAny> = output?;
        let mut upstream: Vec<(String, String)> = Vec::new();
        for source in output.getattr("upstream_columns")?.try_iter()? {
            let source: Bound<'_, PyAny> = source?;
            upstream.push((
                source.getattr("resource_name")?.extract()?,
                source.getattr("column_name")?.extract()?,
            ));
        }
        lineage.push((output.getattr("output_column")?.extract()?, upstream));
    }
    Ok(lineage)
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

/// The names of a model's inferred columns, or `None` when its shape is unknown.
pub(crate) fn inferred_names(model: &Bound<'_, PyAny>) -> PyResult<Option<Vec<String>>> {
    let columns: Bound<'_, PyAny> = model.getattr("inferred_columns")?;
    if columns.is_none() {
        return Ok(None);
    }
    columns
        .try_iter()?
        .map(|column| column?.getattr("name")?.extract())
        .collect::<PyResult<_>>()
        .map(Some)
}

fn blocking_binding_found(models: &[Bound<'_, PyAny>]) -> PyResult<bool> {
    for model in models {
        for item in model.getattr("binding_diagnostics")?.try_iter()? {
            if item?.getattr("is_error")?.is_truthy()? {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn recovery_model(
    model: &Bound<'_, PyAny>,
    binding_results: &Bound<'_, PyAny>,
    (ids, raw_ids): (&Bound<'_, PyDict>, &Bound<'_, PyDict>),
    shared: &StageShared<'_>,
) -> PyResult<RecoveryModel> {
    let name: String = model.getattr("name")?.extract()?;
    let from_session: bool = shared.session_models.contains(&name);
    let bindings: Vec<Bound<'_, PyAny>> = items(&model.getattr("binding_diagnostics")?)?;
    let mut model_bindings: Vec<ModelBinding> = Vec::with_capacity(bindings.len());
    for item in &bindings {
        model_bindings.push(ModelBinding {
            id: id_of(ids, item)?,
            code: item.getattr("code")?.extract()?,
            message: item.getattr("message")?.extract()?,
            is_error: item.getattr("is_error")?.extract()?,
        });
    }
    let mut raw_bindings: Vec<RawBinding> = Vec::new();
    if !bindings.is_empty() {
        let raws: Bound<'_, PyAny> =
            binding_results.call_method1("get", (&name, PyList::empty(model.py())))?;
        for raw in raws.try_iter()? {
            let raw: Bound<'_, PyAny> = raw?;
            raw_bindings.push(RawBinding {
                id: id_of(raw_ids, &raw)?,
                code: raw.get_item(0)?.extract()?,
                message: raw.get_item(1)?.extract()?,
                start: raw.get_item(4)?.extract()?,
                end: raw.get_item(5)?.extract()?,
            });
        }
    }
    let (inferred_columns, lineage) = if from_session {
        let facts = session_model_facts(shared.session, &name).map_err(compiler_error)?;
        (column_names(facts), facts.lineage.clone())
    } else {
        (inferred_names(model)?, lineage_payload(model)?)
    };
    let mut references: Vec<String> = Vec::new();
    for reference in model.getattr("references")?.try_iter()? {
        references.push(reference?.getattr("ref_name")?.extract()?);
    }
    Ok(RecoveryModel {
        name,
        query_sql: model.getattr("query_sql")?.extract()?,
        inferred_columns,
        references,
        lineage: lineage_outputs(lineage),
        bindings: model_bindings,
        raw_bindings,
    })
}

/// Python's revalidation of each planned model with unknown types for poisoned outputs.
fn revalidated<'py>(
    classes: &StageClasses<'py>,
    project: &Bound<'py, PyAny>,
    models: &[usize],
    poisoned: &[(String, String)],
) -> PyResult<Vec<Vec<RevisedBinding>>> {
    if models.is_empty() {
        return Ok(Vec::new());
    }
    let py: Python<'py> = classes.py();
    let shapes: Bound<'py, PyAny> = classes.inputs.call_method1("shapes", (project,))?;
    let unknown: Bound<'py, PyDict> = PyDict::new(py);
    for item in shapes.call_method0("items")?.try_iter()? {
        let (name, columns): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        let copied: Bound<'py, PyDict> = PyDict::new(py);
        copied.update(columns.downcast::<PyDict>()?.as_mapping())?;
        unknown.set_item(name, copied)?;
    }
    for (name, column) in poisoned {
        if let Some(columns) = unknown.get_item(name)?
            && columns.contains(column)?
        {
            columns.set_item(column, UNKNOWN_RECOVERED_TYPE)?;
        }
    }
    let project_models: Bound<'py, PyAny> = project.getattr("models")?;
    let mut revised: Vec<Vec<RevisedBinding>> = Vec::with_capacity(models.len());
    for index in models {
        let request: Bound<'py, PyAny> = classes.call(
            &classes.inputs.getattr("revalidation_request")?,
            &[
                ("project", project),
                ("model", &project_models.get_item(*index)?),
                ("shapes", &unknown.clone().into_any()),
            ],
        )?;
        let result: Bound<'py, PyAny> = classes
            .call(
                &classes.schema_validations,
                &[("requests", &PyTuple::new(py, [request])?.into_any())],
            )?
            .get_item(0)?;
        let mut rows: Vec<RevisedBinding> = Vec::new();
        for item in result.getattr("diagnostics")?.try_iter()? {
            let item: Bound<'py, PyAny> = item?;
            rows.push((
                item.getattr("code")?.extract()?,
                item.getattr("start")?.extract()?,
                item.getattr("end")?.extract()?,
            ));
        }
        revised.push(rows);
    }
    Ok(revised)
}
