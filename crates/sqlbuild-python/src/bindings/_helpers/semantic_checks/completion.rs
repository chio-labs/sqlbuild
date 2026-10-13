//! Native diagnostic recovery, explanations and opt-out rejection after the metadata checks.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyString, PyTuple};
use sqlbuild_analysis::semantic_checks::main::complete_semantic_diagnostics::complete_semantic_diagnostics;
use sqlbuild_analysis::semantic_checks::models::{
    CompletedDiagnostic, CompletionModel, CompletionRequest, SemanticDiagnostic, SemanticLocation,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::semantic_checks::failures::semantic_error;
use crate::bindings::_helpers::semantic_checks::metadata::{ShapeRows, shape_rows};
use crate::bindings::_helpers::semantic_checks::session_facts::{
    column_names, session_model_facts,
};
use crate::bindings::_helpers::semantic_checks::stage_objects::StageClasses;
use crate::bindings::_helpers::semantic_checks::type_recovery::{
    LineageInput, StageShared, diagnostic_ids, id_of, inferred_names, items, lineage_outputs,
    lineage_payload,
};
use crate::bindings::types::CompilerDetach;

const RECOVERED_CODE: &str = "B002";

/// The recovered, explained and opt-out-checked project; a native internal failure raises.
pub(crate) fn completed_diagnostics<'py>(
    classes: &StageClasses<'py>,
    project: &Bound<'py, PyAny>,
    shared: &StageShared<'_>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = classes.py();
    let models: Vec<Bound<'py, PyAny>> = items(&project.getattr("models")?)?;
    let ids: Bound<'py, PyDict> = diagnostic_ids(project, &models)?;
    let diagnostics: Vec<Bound<'py, PyAny>> = items(&project.getattr("diagnostics")?)?;
    let mut recovers: bool = false;
    for item in &diagnostics {
        if item.getattr("code")?.eq(RECOVERED_CODE)? {
            recovers = true;
            break;
        }
    }
    let shapes: ShapeRows = if diagnostics.is_empty() {
        Vec::new()
    } else {
        shape_rows(&classes.inputs.call_method1("shapes", (project,))?)?
    };
    let mut semantic: Vec<SemanticDiagnostic> = Vec::with_capacity(diagnostics.len());
    for item in &diagnostics {
        semantic.push(semantic_diagnostic(item, &ids)?);
    }
    let mut completion_models: Vec<CompletionModel> = Vec::with_capacity(models.len());
    for model in &models {
        completion_models.push(completion_model(model, recovers, shared)?);
    }
    let request = CompletionRequest {
        dialect: project.getattr("sql_analysis_dialect")?.extract()?,
        diagnostics: semantic,
        models: completion_models,
        shapes,
    };
    let (completed, model_bindings, order) = py
        .compiler_detach(|| Ok(complete_semantic_diagnostics(&request, shared.catalog)))
        .map_err(compiler_error)?
        .map_err(|failure| semantic_error(py, &failure))?
        .into_parts();
    let mut rebuilt: Vec<Bound<'py, PyAny>> = Vec::with_capacity(completed.len());
    for row in completed {
        let original: Bound<'py, PyAny> = diagnostics[row.source].clone();
        rebuilt.push(completed_diagnostic(classes, original, row)?);
    }
    let models_value: Bound<'py, PyAny> = match model_bindings {
        None => project.getattr("models")?,
        Some(model_bindings) => {
            let mut updated: Vec<Bound<'py, PyAny>> = Vec::with_capacity(models.len());
            for (model, positions) in models.iter().zip(model_bindings) {
                let selected: Vec<Bound<'py, PyAny>> = positions
                    .into_iter()
                    .map(|position| rebuilt[position].clone())
                    .collect();
                updated.push(classes.call(
                    &classes.with_binding_diagnostics,
                    &[
                        ("model", model),
                        ("diagnostics", &PyTuple::new(py, selected)?.into_any()),
                    ],
                )?);
            }
            PyTuple::new(py, updated)?.into_any()
        }
    };
    let mut ordered: Vec<Bound<'py, PyAny>> = Vec::with_capacity(order.len());
    for entry in order {
        let (position, opt_out) = entry.into_parts();
        if let Some(position) = position {
            ordered.push(rebuilt[position].clone());
        } else if let Some(opt_out) = opt_out {
            let model: &Bound<'py, PyAny> = &models[opt_out.model];
            let notes: Bound<'py, PyAny> = PyTuple::new(py, [opt_out.note])?.into_any();
            ordered.push(classes.call(
                &classes.diagnostic,
                &[
                    ("phase", &classes.compile_phase),
                    ("severity", &classes.error),
                    ("code", &classes.opt_out_code),
                    ("message", &PyString::new(py, &opt_out.message).into_any()),
                    ("resource_type", &classes.model_resource),
                    ("resource_name", &model.getattr("name")?),
                    ("location", &model.getattr("rejected_sql_analysis_opt_out")?),
                    ("notes", &notes),
                    ("help", &PyString::new(py, &opt_out.help).into_any()),
                ],
            )?);
        }
    }
    classes.project_with(
        project,
        &[
            ("models", &models_value),
            ("diagnostics", &PyTuple::new(py, ordered)?.into_any()),
        ],
    )
}

fn optional_location(location: &Bound<'_, PyAny>) -> PyResult<Option<SemanticLocation>> {
    if location.is_none() {
        return Ok(None);
    }
    Ok(Some(SemanticLocation {
        line: location.getattr("line")?.extract()?,
        column: location.getattr("column")?.extract()?,
        end_line: location.getattr("end_line")?.extract()?,
        end_column: location.getattr("end_column")?.extract()?,
    }))
}

fn semantic_diagnostic(
    item: &Bound<'_, PyAny>,
    ids: &Bound<'_, PyDict>,
) -> PyResult<SemanticDiagnostic> {
    let resource_type: Bound<'_, PyAny> = item.getattr("resource_type")?;
    Ok(SemanticDiagnostic {
        id: id_of(ids, item)?,
        code: item.getattr("code")?.extract()?,
        message: item.getattr("message")?.extract()?,
        resource_type: if resource_type.is_none() {
            None
        } else {
            Some(resource_type.str()?.extract()?)
        },
        resource_name: item.getattr("resource_name")?.extract()?,
        line: item.getattr("line")?.extract()?,
        column: item.getattr("column")?.extract()?,
        location: optional_location(&item.getattr("location")?)?,
        help: item.getattr("help")?.extract()?,
        notes: items(&item.getattr("notes")?)?
            .iter()
            .map(PyAnyMethods::extract)
            .collect::<PyResult<_>>()?,
    })
}

fn completion_model(
    model: &Bound<'_, PyAny>,
    recovers: bool,
    shared: &StageShared<'_>,
) -> PyResult<CompletionModel> {
    let name: String = model.getattr("name")?.extract()?;
    let from_session: bool = shared.session_models.contains(&name);
    let inferred_columns: Vec<String> = if from_session {
        column_names(session_model_facts(shared.session, &name).map_err(compiler_error)?)
            .unwrap_or_default()
    } else {
        inferred_names(model)?.unwrap_or_default()
    };
    let lineage: Vec<LineageInput> = if !recovers {
        Vec::new()
    } else if from_session {
        session_model_facts(shared.session, &name)
            .map_err(compiler_error)?
            .lineage
            .clone()
    } else {
        lineage_payload(model)?
    };
    let opt_out: Bound<'_, PyAny> = model.getattr("rejected_sql_analysis_opt_out")?;
    let mut binding_codes: Vec<String> = Vec::new();
    for item in model.getattr("binding_diagnostics")?.try_iter()? {
        binding_codes.push(item?.getattr("code")?.extract()?);
    }
    Ok(CompletionModel {
        name,
        query_sql: model.getattr("query_sql")?.extract()?,
        authored_sql: model.getattr("authored_sql")?.extract()?,
        inferred_columns,
        lineage: lineage_outputs(lineage),
        binding_codes,
        rejected_opt_out_file: if opt_out.is_none() {
            None
        } else {
            Some(opt_out.getattr("path")?.getattr("name")?.extract()?)
        },
    })
}

fn completed_diagnostic<'py>(
    classes: &StageClasses<'py>,
    original: Bound<'py, PyAny>,
    row: CompletedDiagnostic,
) -> PyResult<Bound<'py, PyAny>> {
    if !row.changed {
        return Ok(original);
    }
    let py: Python<'py> = classes.py();
    let mut current: Bound<'py, PyAny> = original.getattr("location")?;
    if let (Some(existing), Some(location)) = (optional_location(&current)?, row.location.as_ref())
        && (
            existing.line,
            existing.column,
            existing.end_line,
            existing.end_column,
        ) != (
            location.line,
            location.column,
            location.end_line,
            location.end_column,
        )
    {
        current = classes.replaced(
            &current,
            &[
                ("line", &location.line.into_bound_py_any(py)?),
                ("column", &location.column.into_bound_py_any(py)?),
                ("end_line", &location.end_line.into_bound_py_any(py)?),
                ("end_column", &location.end_column.into_bound_py_any(py)?),
            ],
        )?;
    }
    classes.replaced(
        &original,
        &[
            ("message", &PyString::new(py, &row.message).into_any()),
            ("help", &row.help.into_bound_py_any(py)?),
            ("notes", &PyTuple::new(py, row.notes)?.into_any()),
            ("location", &current),
            ("line", &row.line.into_bound_py_any(py)?),
            ("column", &row.column.into_bound_py_any(py)?),
        ],
    )
}
