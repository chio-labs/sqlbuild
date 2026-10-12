//! The scope lookup of a full scope index: canonical orders, mappings, targets and visibility.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::text::main::python_str_repr::python_str_repr;
use sqlbuild_scopes::scope_index::main::normalize_scope_path::normalize_scope_path;
use sqlbuild_scopes::scope_index::main::report_lookup::report_lookup;
use sqlbuild_scopes::scope_index::main::report_target::report_target;
use sqlbuild_scopes::scope_index::main::resolve_report_visibility::resolve_report_visibility;
use sqlbuild_scopes::scope_index::models::{
    GrantKind, IdentityFailure, KeyedGroups, RejectedPath, ReportDiagnosticKey, ReportGrant,
    ReportLookup, ReportRecords, ReportTarget, ReportUsage, ResolvedVisibility, ResolvedVisible,
    ScopePathFailure, TargetFailure, TargetMatch,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::scopes::placement::{
    DeclarationRow, IdentityRow, QualifiedRow, ResourceRow, RootRow, declaration_identity,
    declaration_record, ownership_root, qualified_identity, resource_identity, resource_record,
};
use crate::bindings::types::CompilerDetach;

/// Consumer, declaration, usage kind and what the consumer uses it through.
type UsageRow = (QualifiedRow, QualifiedRow, String, Option<QualifiedRow>);
/// Resource, declaration, what it came through, and the grant kind.
type GrantRow = (IdentityRow, QualifiedRow, QualifiedRow, String);
/// Path, line, column and code of a diagnostic.
type DiagnosticKeyRow = (Option<String>, Option<i64>, Option<i64>, String);
/// Every record of a full scope index as rows.
type RecordRows = (
    Vec<RootRow>,
    Vec<ResourceRow>,
    Vec<DeclarationRow>,
    Vec<UsageRow>,
    Vec<GrantRow>,
    Vec<DiagnosticKeyRow>,
);
type GroupRows = Vec<Vec<usize>>;
/// Roots, resources, declarations, usages, grants and diagnostics in canonical order.
type OrderRows = (
    Vec<usize>,
    Vec<usize>,
    Vec<usize>,
    Vec<usize>,
    Vec<usize>,
    Vec<usize>,
);
/// Each mapping's groups, then every input resource's normalized path key.
type MappingRows = (
    GroupRows,
    GroupRows,
    GroupRows,
    GroupRows,
    GroupRows,
    GroupRows,
    Vec<String>,
);
/// Global, private, local and inherited canonical declaration positions.
type VisibilityRows = (
    Vec<usize>,
    Vec<(IdentityRow, Vec<usize>)>,
    Vec<(String, Vec<usize>)>,
    Vec<(String, Vec<usize>)>,
);
/// The canonical orders, mappings and visibility groups, else the rejected path's message.
type LookupRows = (
    Option<(OrderRows, MappingRows, VisibilityRows)>,
    Option<String>,
);
/// `(declarations, canonical positions)` matched, else identity and path error messages.
type TargetRows = (bool, Vec<usize>, Option<String>, Option<String>);
/// Visible `(position, reason, grant)`, inaccessible `(position, reason)`, else the path error.
type ResolvedRows = (
    Vec<(usize, &'static str, Option<usize>)>,
    Vec<(usize, &'static str)>,
    Option<String>,
);

/// One full scope index's records and lookup, kept for targets and classification.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeScopeLookup {
    pub(crate) records: ReportRecords,
    pub(crate) lookup: ReportLookup,
    /// Each input resource, declaration and grant's canonical position.
    canonical: CanonicalPositions,
}

/// The inverse of the lookup's canonical orders.
struct CanonicalPositions {
    resources: Vec<usize>,
    declarations: Vec<usize>,
    grants: Vec<usize>,
}

fn inverse(order: &[usize]) -> Vec<usize> {
    let mut positions: Vec<usize> = vec![0; order.len()];
    for (canonical, input) in order.iter().enumerate() {
        positions[*input] = canonical;
    }
    positions
}

pub(crate) fn grant_kind(value: &str) -> PyResult<GrantKind> {
    match value {
        "expected_model" => Ok(GrantKind::ExpectedModel),
        "tested_macro" => Ok(GrantKind::TestedMacro),
        _ => Err(pyo3::exceptions::PyValueError::new_err(
            "invalid scope grant kind",
        )),
    }
}

fn report_records(rows: RecordRows) -> PyResult<ReportRecords> {
    let (roots, resources, declarations, usages, grants, diagnostics) = rows;
    let mut records: ReportRecords = ReportRecords::default();
    for root in roots {
        records.roots.push(ownership_root(root)?);
    }
    for row in resources {
        records.resources.push(resource_record(row)?);
    }
    for row in declarations {
        records.declarations.push(declaration_record(row)?);
    }
    for (consumer, declaration, kind, through) in usages {
        records.usages.push(ReportUsage {
            consumer: qualified_identity(consumer)?,
            declaration: declaration_identity(declaration)?,
            kind,
            through: through.map(qualified_identity).transpose()?,
        });
    }
    for (resource, declaration, through, kind) in grants {
        records.grants.push(ReportGrant {
            resource: resource_identity(resource)?,
            declaration: declaration_identity(declaration)?,
            through: qualified_identity(through)?,
            kind: grant_kind(&kind)?,
        });
    }
    for (path, line, column, code) in diagnostics {
        records.diagnostics.push(ReportDiagnosticKey {
            path,
            line,
            column,
            code,
        });
    }
    Ok(records)
}

/// Python's `InvalidScopePathError` message for a rejected path.
pub(crate) fn path_message(rejected: &RejectedPath) -> String {
    match rejected.failure {
        ScopePathFailure::NotProjectRelative => {
            format!("Scope path must be project-relative: {}", rejected.path)
        }
        ScopePathFailure::EscapesProject => {
            format!("Scope path escapes the project: {}", rejected.path)
        }
    }
}

/// Python's `InvalidQualifiedIdentityError` message for a rejected identity.
pub(crate) fn identity_message(failure: &IdentityFailure, value: &str) -> String {
    let shown = |text: &str| -> String { python_str_repr(text) };
    match failure {
        IdentityFailure::NoName => format!("Qualified identity has no name: {}", shown(value)),
        IdentityFailure::UnknownKind(kind) => {
            format!("Unknown qualified identity kind: {}", shown(kind))
        }
        IdentityFailure::InvalidPrivate => format!("Invalid private identity: {}", shown(value)),
        IdentityFailure::Unqualified => format!(
            "Expected a kind-qualified identity such as 'model:name': {}",
            shown(value)
        ),
    }
}

fn group_rows(groups: KeyedGroups) -> GroupRows {
    groups.groups
}

fn lookup_rows(lookup: &ReportLookup) -> (OrderRows, MappingRows, VisibilityRows) {
    let groups = lookup.groups.clone();
    let visibility = lookup.visibility.clone();
    (
        (
            lookup.roots.clone(),
            lookup.resources.clone(),
            lookup.declarations.clone(),
            lookup.usages.clone(),
            lookup.grants.clone(),
            lookup.diagnostics.clone(),
        ),
        (
            group_rows(groups.resources),
            group_rows(groups.resources_by_path),
            group_rows(groups.declarations),
            group_rows(groups.usages_by_consumer),
            group_rows(groups.usages_by_declaration),
            group_rows(groups.grants_by_resource),
            lookup.resource_paths.clone(),
        ),
        (
            visibility.global,
            visibility
                .private
                .into_iter()
                .map(|(owner, positions)| ((owner.kind.as_str().to_owned(), owner.name), positions))
                .collect(),
            visibility.local,
            visibility.inherited,
        ),
    )
}

/// Input positions as canonical positions.
fn canonical(order: &[usize], positions: Vec<usize>) -> Vec<usize> {
    positions
        .into_iter()
        .map(|position| order[position])
        .collect()
}

#[pymethods]
impl NativeScopeLookup {
    /// The records `target` names: an identity row, else qualified identity or path text.
    fn target(&self, identity: Option<QualifiedRow>, text: &str) -> PyResult<TargetRows> {
        let target: ReportTarget = match identity {
            Some(row) => ReportTarget::Identity(qualified_identity(row)?),
            None => ReportTarget::Text(text.to_owned()),
        };
        Ok(match report_target(&self.records, &self.lookup, &target) {
            Ok(TargetMatch::Resources(positions)) => (
                false,
                canonical(&self.canonical.resources, positions),
                None,
                None,
            ),
            Ok(TargetMatch::Declarations(positions)) => (
                true,
                canonical(&self.canonical.declarations, positions),
                None,
                None,
            ),
            Err(TargetFailure::Identity(failure)) => (
                false,
                Vec::new(),
                Some(identity_message(&failure, text)),
                None,
            ),
            Err(TargetFailure::Path(rejected)) => {
                (false, Vec::new(), None, Some(path_message(&rejected)))
            }
        })
    }

    /// Python's `_classify_resource` of one resource, with inaccessible reasons.
    fn resolve(&self, py: Python<'_>, resource: ResourceRow) -> PyResult<ResolvedRows> {
        let resource = resource_record(resource)?;
        let (records, lookup) = (&self.records, &self.lookup);
        let resolved = py
            .compiler_detach(|| Ok(resolve_report_visibility(records, lookup, &resource)))
            .map_err(compiler_error)?;
        Ok(match resolved {
            Ok(resolved) => resolved_rows(resolved, &self.canonical.grants),
            Err(rejected) => (Vec::new(), Vec::new(), Some(path_message(&rejected))),
        })
    }
}

fn visible_row(entry: ResolvedVisible, grants: &[usize]) -> (usize, &'static str, Option<usize>) {
    let grant: Option<usize> = entry.grant.map(|grant| grants[grant]);
    (entry.position, entry.reason.as_str(), grant)
}

fn resolved_rows(resolved: ResolvedVisibility, grants: &[usize]) -> ResolvedRows {
    let visible: Vec<(usize, &'static str, Option<usize>)> = resolved
        .visible
        .into_iter()
        .map(|entry| visible_row(entry, grants))
        .collect();
    (
        visible,
        resolved
            .inaccessible
            .into_iter()
            .map(|(position, reason)| (position, reason.as_str()))
            .collect(),
        None,
    )
}

/// The lookup of a full scope index's records, else the message of the path Python rejects.
#[pyfunction]
fn build_native_scope_lookup(
    py: Python<'_>,
    rows: RecordRows,
) -> PyResult<(Option<NativeScopeLookup>, LookupRows)> {
    let records: ReportRecords = report_records(rows)?;
    let built = py
        .compiler_detach(|| Ok(report_lookup(&records)))
        .map_err(compiler_error)?;
    Ok(match built {
        Ok(lookup) => {
            let rows: (OrderRows, MappingRows, VisibilityRows) = lookup_rows(&lookup);
            let canonical: CanonicalPositions = CanonicalPositions {
                resources: inverse(&lookup.resources),
                declarations: inverse(&lookup.declarations),
                grants: inverse(&lookup.grants),
            };
            let native: NativeScopeLookup = NativeScopeLookup {
                records,
                lookup,
                canonical,
            };
            (Some(native), (Some(rows), None))
        }
        Err(rejected) => (None, (None, Some(path_message(&rejected)))),
    })
}

/// Python's scope `normalize_path`, else the `InvalidScopePathError` message.
#[pyfunction]
fn scope_normalize_path(path: &str) -> (Option<String>, Option<String>) {
    match normalize_scope_path(path) {
        Ok(normalized) => (Some(normalized), None),
        Err(failure) => (
            None,
            Some(path_message(&RejectedPath {
                failure,
                path: path.to_owned(),
            })),
        ),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeScopeLookup>()?;
    module.add_function(wrap_pyfunction!(build_native_scope_lookup, module)?)?;
    module.add_function(wrap_pyfunction!(scope_normalize_path, module)?)?;
    Ok(())
}
