//! Native diagnostic recovery, explanations and opt-out rejection.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyRef, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::semantic_checks::main::complete_semantic_diagnostics::complete_semantic_diagnostics;
use sqlbuild_analysis::semantic_checks::models::{
    CompletedDiagnostic, CompletionModel, CompletionRequest, FinalDiagnostic, SemanticDiagnostic,
    SemanticLocation,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::semantic_checks::type_recovery::{LineageInput, lineage_outputs};
use crate::bindings::models::ProjectCatalog;
use crate::bindings::types::CompilerDetach;

/// `(line, column, end_line, end_column)`.
type LocationRow = (i64, i64, Option<i64>, Option<i64>);
/// `(id, code, message, resource_type, resource_name, line, column, location, help, notes)`.
type DiagnosticInput = (
    usize,
    String,
    String,
    Option<String>,
    Option<String>,
    Option<i64>,
    Option<i64>,
    Option<LocationRow>,
    Option<String>,
    Vec<String>,
);
/// `(name, query_sql, authored_sql, inferred names, lineage, binding codes, opt-out file)`.
type ModelInput = (
    String,
    String,
    String,
    Vec<String>,
    Vec<LineageInput>,
    Vec<String>,
    Option<String>,
);
/// `(dialect, diagnostics, models, shapes)`.
type RequestInput = (
    Option<String>,
    Vec<DiagnosticInput>,
    Vec<ModelInput>,
    Vec<(String, Vec<(String, String)>)>,
);
/// `(source, message, help, notes, location, line, column, changed)`.
type CompletedRow = (
    usize,
    String,
    Option<String>,
    Vec<String>,
    Option<LocationRow>,
    Option<i64>,
    Option<i64>,
    bool,
);
/// `(completed position, (model, message, note, help))`: exactly one side is set.
type OrderRow = (Option<usize>, Option<(usize, String, String, String)>);
/// `(deferral, completed, model binding positions, order)`.
type OutcomeRow = (
    Option<&'static str>,
    Vec<CompletedRow>,
    Option<Vec<Vec<usize>>>,
    Vec<OrderRow>,
);

/// Recover, explain and reject opt-outs on `catalog`'s analysis pool.
#[pyfunction]
fn complete_semantic_checks(
    py: Python<'_>,
    catalog: PyRef<'_, ProjectCatalog>,
    request: RequestInput,
) -> PyResult<OutcomeRow> {
    let request = completion_request(request);
    let catalog = &catalog.inner;
    let outcome = py
        .compiler_detach(|| complete_semantic_diagnostics(&request, catalog))
        .map_err(compiler_error)?;
    let (deferral, parts) = outcome.into_parts();
    let (diagnostics, model_bindings, order) = parts.unwrap_or_default();
    Ok((
        deferral,
        diagnostics.into_iter().map(completed_row).collect(),
        model_bindings,
        order.into_iter().map(order_row).collect(),
    ))
}

fn location(row: LocationRow) -> SemanticLocation {
    SemanticLocation {
        line: row.0,
        column: row.1,
        end_line: row.2,
        end_column: row.3,
    }
}

fn location_row(location: SemanticLocation) -> LocationRow {
    (
        location.line,
        location.column,
        location.end_line,
        location.end_column,
    )
}

fn completion_request((dialect, diagnostics, models, shapes): RequestInput) -> CompletionRequest {
    CompletionRequest {
        dialect,
        diagnostics: diagnostics.into_iter().map(semantic_diagnostic).collect(),
        models: models.into_iter().map(completion_model).collect(),
        shapes,
    }
}

fn semantic_diagnostic(
    (id, code, message, resource_type, resource_name, line, column, place, help, notes): DiagnosticInput,
) -> SemanticDiagnostic {
    SemanticDiagnostic {
        id,
        code,
        message,
        resource_type,
        resource_name,
        line,
        column,
        location: place.map(location),
        help,
        notes,
    }
}

fn completion_model(
    (name, query_sql, authored_sql, inferred_columns, lineage, binding_codes, opt_out): ModelInput,
) -> CompletionModel {
    CompletionModel {
        name,
        query_sql,
        authored_sql,
        inferred_columns,
        lineage: lineage_outputs(lineage),
        binding_codes,
        rejected_opt_out_file: opt_out,
    }
}

fn completed_row(diagnostic: CompletedDiagnostic) -> CompletedRow {
    (
        diagnostic.source,
        diagnostic.message,
        diagnostic.help,
        diagnostic.notes,
        diagnostic.location.map(location_row),
        diagnostic.line,
        diagnostic.column,
        diagnostic.changed,
    )
}

fn order_row(entry: FinalDiagnostic) -> OrderRow {
    let (position, opt_out) = entry.into_parts();
    (
        position,
        opt_out.map(|opt_out| (opt_out.model, opt_out.message, opt_out.note, opt_out.help)),
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(complete_semantic_checks, module)?)?;
    Ok(())
}
