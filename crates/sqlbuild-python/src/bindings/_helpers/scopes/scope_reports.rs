//! `sqb scope` reports over a native scope lookup, their serialization and the metadata projection.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, Py, PyAny, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::json::models::JsonValue;
use sqlbuild_scopes::scope_report::main::browse_scope_folders::browse_scope_folders;
use sqlbuild_scopes::scope_report::main::build_scope_report::build_scope_report;
use sqlbuild_scopes::scope_report::main::explain_scope_declaration::explain_scope_declaration;
use sqlbuild_scopes::scope_report::main::list_scope_declarations::list_scope_declarations;
use sqlbuild_scopes::scope_report::main::preview_scope_move::preview_scope_move;
use sqlbuild_scopes::scope_report::main::scope_metadata_projection::scope_metadata_projection;
use sqlbuild_scopes::scope_report::main::serialize_scope_result::serialize_scope_result;
use sqlbuild_scopes::scope_report::models::{
    ExplainRequest, FolderRequest, MoveRequest, ProjectionGrant, ProjectionIndex,
    ProjectionStanding, ProjectionUsage, ReportFailure, ReportRequest, ReportSource, ReportValues,
    ScopeResult,
};

use crate::bindings::_helpers::scopes::placement::{
    DeclarationRow, IdentityRow, QualifiedRow, ResourceRow, RootRow, declaration_identity,
    declaration_record, ownership_root, qualified_identity, resource_identity, resource_record,
};
use crate::bindings::_helpers::scopes::scope_lookup::{
    NativeScopeLookup, grant_kind, identity_message, path_message,
};
use crate::bindings::_helpers::scopes::scope_report_rows::{
    BrowseOutRow, BrowseRow, CompletenessRow, DiagnosticInRow, ExplanationOutRow, FiltersRow,
    ListOutRow, ListRow, MoveOutRow, ReportOutRow, ReportRow, TargetRow, ValuesRow, browse_in,
    browse_out, completeness, declaration_target, declaration_values, diagnostic_facts,
    explanation_out, filters, json_to_python, list_in, list_out, move_out, raised_out, report_in,
    report_out, target,
};

type PyObject = Py<PyAny>;

/// `(kind, message)` of the scope error Python raises: `path` or `identity`.
type FailureRow = Option<(&'static str, String)>;
/// Consumer, declaration, usage kind, what it came through and the enum member.
type UsageRow = (
    QualifiedRow,
    QualifiedRow,
    String,
    Option<QualifiedRow>,
    Option<String>,
);
/// Resource, declaration, through and grant kind.
type GrantRow = (IdentityRow, QualifiedRow, QualifiedRow, String);
/// Resource, declaration, reason and what it came through.
type StandingRow = (IdentityRow, QualifiedRow, String, Option<QualifiedRow>);
/// Every `ScopeIndex` tuple, with declaration values parallel to the declarations.
type ProjectionRows = (
    Vec<RootRow>,
    Vec<ResourceRow>,
    Vec<DeclarationRow>,
    Vec<ValuesRow>,
    Vec<UsageRow>,
    Vec<GrantRow>,
    Vec<StandingRow>,
    Vec<StandingRow>,
    Vec<DiagnosticInRow>,
    CompletenessRow,
);
type ReportRequestRow = (Option<TargetRow>, Option<String>, bool, FiltersRow);
type ExplainRequestRow = (
    (Option<QualifiedRow>, String),
    Option<TargetRow>,
    Option<String>,
    bool,
);
type FolderRequestRow = (String, Option<TargetRow>, bool, Option<FiltersRow>);

fn failure_row(failure: &ReportFailure) -> PyResult<FailureRow> {
    match failure {
        ReportFailure::Path(rejected) => Ok(Some(("path", path_message(rejected)))),
        ReportFailure::Identity(failure, text) => {
            Ok(Some(("identity", identity_message(failure, text))))
        }
        ReportFailure::Serialization(message) => Err(PyValueError::new_err(message.clone())),
        ReportFailure::IndexOutOfRange => {
            Ok(Some(("index", "tuple index out of range".to_owned())))
        }
    }
}

/// One lookup's reports: the lookup and every declaration's values in input order.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeScopeReports {
    lookup: Py<NativeScopeLookup>,
    values: ReportValues,
}

impl NativeScopeReports {
    fn source<'a>(&'a self, lookup: &'a NativeScopeLookup) -> ReportSource<'a> {
        ReportSource {
            records: &lookup.records,
            lookup: &lookup.lookup,
            values: &self.values,
        }
    }
}

#[pymethods]
impl NativeScopeReports {
    /// `query_scope_report`.
    fn report(
        &self,
        py: Python<'_>,
        request: ReportRequestRow,
    ) -> PyResult<(Option<ReportOutRow>, FailureRow)> {
        let (target_row, at, directory, filter_row) = request;
        let request: ReportRequest = ReportRequest {
            target: target_row.map(target).transpose()?,
            at,
            directory,
            filters: filters(filter_row),
        };
        let lookup = self.lookup.get();
        match build_scope_report(self.source(lookup), &request) {
            Ok(report) => Ok((Some(report_out(py, report)?), None)),
            Err(failure) => Ok((None, failure_row(&failure)?)),
        }
    }

    /// `explain_scope_declaration`.
    fn explain(
        &self,
        py: Python<'_>,
        request: ExplainRequestRow,
    ) -> PyResult<(Option<ExplanationOutRow>, FailureRow)> {
        let (declaration, target_row, at, directory) = request;
        let request: ExplainRequest = ExplainRequest {
            declaration: declaration_target(declaration)?,
            target: target_row.map(target).transpose()?,
            at,
            directory,
        };
        let lookup = self.lookup.get();
        match explain_scope_declaration(self.source(lookup), &request) {
            Ok((explanation, diagnostics)) => Ok((
                Some((explanation_out(py, explanation)?, raised_out(diagnostics))),
                None,
            )),
            Err(failure) => Ok((None, failure_row(&failure)?)),
        }
    }

    /// `browse_scope_folders`.
    fn browse(&self, request: FolderRequestRow) -> PyResult<BrowseOutRow> {
        let request: FolderRequest = folder_request(request)?;
        let lookup = self.lookup.get();
        Ok(browse_out(browse_scope_folders(
            self.source(lookup),
            &request,
        )))
    }

    /// `list_scope_declarations`.
    fn list(
        &self,
        py: Python<'_>,
        request: FolderRequestRow,
    ) -> PyResult<(Option<ListOutRow>, FailureRow)> {
        let request: FolderRequest = folder_request(request)?;
        let lookup = self.lookup.get();
        match list_scope_declarations(self.source(lookup), &request) {
            Ok(result) => Ok((Some(list_out(py, result)?), None)),
            Err(failure) => Ok((None, failure_row(&failure)?)),
        }
    }

    /// `preview_scope_move`.
    fn move_preview(
        &self,
        py: Python<'_>,
        request: (TargetRow, String),
    ) -> PyResult<(Option<MoveOutRow>, FailureRow)> {
        let request: MoveRequest = MoveRequest {
            resource: target(request.0)?,
            destination: request.1,
        };
        let lookup = self.lookup.get();
        match preview_scope_move(self.source(lookup), &request) {
            Ok((preview, diagnostics)) => Ok((
                Some((
                    preview.map(|preview| move_out(py, preview)).transpose()?,
                    raised_out(diagnostics),
                )),
                None,
            )),
            Err(failure) => Ok((None, failure_row(&failure)?)),
        }
    }
}

fn folder_request(row: FolderRequestRow) -> PyResult<FolderRequest> {
    let (folder, target_row, prospective, filter_row) = row;
    Ok(FolderRequest {
        folder,
        target: target_row.map(target).transpose()?,
        prospective,
        filters: filter_row.map(filters),
    })
}

/// The reports of `lookup`, with each canonical declaration's values and the completeness.
#[pyfunction]
fn build_native_scope_reports(
    lookup: Py<NativeScopeLookup>,
    values: (Vec<ValuesRow>, CompletenessRow),
) -> PyResult<NativeScopeReports> {
    let (rows, completeness_row) = values;
    let native: &NativeScopeLookup = lookup.get();
    let canonical: &[usize] = &native.lookup.declarations;
    if rows.len() != canonical.len() {
        return Err(PyValueError::new_err(
            "scope report values must match the lookup's declarations",
        ));
    }
    let mut declarations = vec![Default::default(); canonical.len()];
    for (position, row) in canonical.iter().zip(rows) {
        declarations[*position] = declaration_values(row)?;
    }
    Ok(NativeScopeReports {
        lookup,
        values: ReportValues {
            declarations,
            completeness: completeness(completeness_row),
        },
    })
}

/// `serialize_scope_report` of a `report`, `browse` or `list` result row.
#[pyfunction]
fn serialize_scope_result_row(kind: &str, row: &Bound<'_, PyAny>) -> PyResult<String> {
    use pyo3::prelude::PyAnyMethods;
    let result: ScopeResult = match kind {
        "report" => ScopeResult::Report(Box::new(report_in(
            row.extract::<ReportRow<Bound<'_, PyAny>, DiagnosticInRow>>()?,
        )?)),
        "browse" => ScopeResult::Browse(browse_in(row.extract::<BrowseRow<DiagnosticInRow>>()?)?),
        _ => ScopeResult::List(list_in(
            row.extract::<ListRow<Bound<'_, PyAny>, DiagnosticInRow>>()?,
        )?),
    };
    serialize_scope_result(&result).map_err(|failure| match failure {
        ReportFailure::Serialization(message) => PyValueError::new_err(message),
        other => PyValueError::new_err(format!("{other:?}")),
    })
}

fn projection_index(rows: ProjectionRows) -> PyResult<ProjectionIndex> {
    let (
        roots,
        resources,
        declarations,
        values,
        usages,
        grants,
        visibility,
        inaccessible,
        diagnostics,
        completeness_row,
    ) = rows;
    let standing =
        |(resource, declaration, reason, through): StandingRow| -> PyResult<ProjectionStanding> {
            Ok(ProjectionStanding {
                resource: resource_identity(resource)?,
                declaration: declaration_identity(declaration)?,
                reason,
                through: through.map(qualified_identity).transpose()?,
            })
        };
    Ok(ProjectionIndex {
        roots: roots
            .into_iter()
            .map(ownership_root)
            .collect::<PyResult<_>>()?,
        resources: resources
            .into_iter()
            .map(resource_record)
            .collect::<PyResult<_>>()?,
        declarations: declarations
            .into_iter()
            .map(declaration_record)
            .collect::<PyResult<_>>()?,
        values: ReportValues {
            declarations: values
                .into_iter()
                .map(declaration_values)
                .collect::<PyResult<_>>()?,
            completeness: completeness(completeness_row),
        },
        usages: usages
            .into_iter()
            .map(|(consumer, declaration, kind, through, enum_member)| {
                Ok(ProjectionUsage {
                    consumer: qualified_identity(consumer)?,
                    declaration: declaration_identity(declaration)?,
                    kind,
                    through: through.map(qualified_identity).transpose()?,
                    enum_member,
                })
            })
            .collect::<PyResult<_>>()?,
        grants: grants
            .into_iter()
            .map(|(resource, declaration, through, kind)| {
                Ok(ProjectionGrant {
                    resource: resource_identity(resource)?,
                    declaration: declaration_identity(declaration)?,
                    through: qualified_identity(through)?,
                    kind: grant_kind(&kind)?,
                })
            })
            .collect::<PyResult<_>>()?,
        visibility: visibility
            .into_iter()
            .map(standing)
            .collect::<PyResult<_>>()?,
        inaccessible: inaccessible
            .into_iter()
            .map(standing)
            .collect::<PyResult<_>>()?,
        diagnostics: diagnostics
            .into_iter()
            .map(diagnostic_facts)
            .collect::<PyResult<_>>()?,
    })
}

/// `scope_metadata_projection` of one index's rows, as the dictionary Python builds.
#[pyfunction]
fn scope_metadata_projection_rows(py: Python<'_>, rows: ProjectionRows) -> PyResult<PyObject> {
    let index: ProjectionIndex = projection_index(rows)?;
    let projection: JsonValue = scope_metadata_projection(&index);
    json_to_python(py, projection, false)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeScopeReports>()?;
    module.add_function(wrap_pyfunction!(build_native_scope_reports, module)?)?;
    module.add_function(wrap_pyfunction!(serialize_scope_result_row, module)?)?;
    module.add_function(wrap_pyfunction!(scope_metadata_projection_rows, module)?)?;
    Ok(())
}
