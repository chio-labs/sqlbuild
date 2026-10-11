//! The persistent scope index cache: fingerprint, verified read and atomic write.

use std::path::PathBuf;

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_scopes::scope_cache::main::encode_scope_cache::encode_scope_cache;
use sqlbuild_scopes::scope_cache::main::read_scope_cache::read_scope_cache;
use sqlbuild_scopes::scope_cache::main::scope_fingerprint::scope_fingerprint;
use sqlbuild_scopes::scope_cache::main::write_scope_cache::write_scope_cache;
use sqlbuild_scopes::scope_cache::models::{
    CachedDeclaration, CachedDiagnostic, CachedInaccessible, CachedIndex, CachedUsage,
    CachedVisibility, ConstantFacts, EnumFacts, Fingerprint, FingerprintInputs, MacroFacts,
};
use sqlbuild_scopes::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, GrantKind, OwnershipRoot, QualifiedIdentity,
    ReportGrant, ResourceIdentity, ResourceKind, ResourceRecord,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::scopes::placement::{
    DeclarationRow, IdentityRow, QualifiedRow, ResourceRow, RootRow, declaration_identity,
    declaration_record, ownership_root, qualified_identity, resource_identity, resource_record,
};
use crate::bindings::types::CompilerDetach;

/// Parameters, dependencies and source digest of a macro.
type MacroRow = (Vec<String>, Vec<QualifiedRow>, String);
/// Member names and scalar type of an enum.
type EnumRow = (Vec<String>, String);
/// Logical type, collection kind, item count, nullability and rendering of a constant.
type ConstantRow = (String, Option<String>, Option<i64>, bool, Option<String>);
type FullDeclarationRow = (
    DeclarationRow,
    Option<MacroRow>,
    Option<EnumRow>,
    Option<ConstantRow>,
);
type UsageRow = (
    QualifiedRow,
    QualifiedRow,
    String,
    Option<QualifiedRow>,
    Option<String>,
);
type GrantRow = (IdentityRow, QualifiedRow, QualifiedRow, String);
type VisibilityRow = (IdentityRow, QualifiedRow, String, Option<QualifiedRow>);
type InaccessibleRow = (IdentityRow, QualifiedRow, String);
type DiagnosticRow = (
    String,
    String,
    String,
    Option<String>,
    Option<i64>,
    Option<i64>,
    Option<QualifiedRow>,
    Option<IdentityRow>,
);
type Completeness = (bool, bool, bool, bool, bool, bool);
/// Every field of a full scope index as rows.
type IndexRows = (
    Vec<RootRow>,
    Vec<ResourceRow>,
    Vec<FullDeclarationRow>,
    Vec<UsageRow>,
    Vec<GrantRow>,
    Vec<VisibilityRow>,
    Vec<InaccessibleRow>,
    Vec<DiagnosticRow>,
    Completeness,
);
/// Config files, candidate roots, declaration folders, named declaration folders, version.
type FingerprintRow = (Vec<String>, Vec<String>, Vec<String>, Vec<String>, String);

fn invalid(what: &str) -> pyo3::PyErr {
    PyValueError::new_err(format!("invalid scope cache {what}"))
}

fn grant_kind(value: &str) -> PyResult<GrantKind> {
    [GrantKind::ExpectedModel, GrantKind::TestedMacro]
        .into_iter()
        .find(|kind| kind.as_str() == value)
        .ok_or_else(|| invalid("grant kind"))
}

fn optional_identity(row: Option<QualifiedRow>) -> PyResult<Option<QualifiedIdentity>> {
    row.map(qualified_identity).transpose()
}

fn full_declaration(row: FullDeclarationRow) -> PyResult<CachedDeclaration> {
    let (record, macro_row, enum_row, constant_row) = row;
    let macro_facts: Option<MacroFacts> = match macro_row {
        None => None,
        Some((parameters, dependencies, source_digest)) => Some(MacroFacts {
            parameters,
            dependencies: dependencies
                .into_iter()
                .map(declaration_identity)
                .collect::<PyResult<_>>()?,
            source_digest,
        }),
    };
    Ok(CachedDeclaration {
        record: declaration_record(record)?,
        macro_facts,
        enum_facts: enum_row.map(|(members, scalar_type)| EnumFacts {
            members,
            scalar_type,
        }),
        constant_facts: constant_row.map(
            |(logical_type, collection_kind, item_count, nullable, render_as)| ConstantFacts {
                logical_type,
                collection_kind,
                item_count,
                nullable,
                render_as,
            },
        ),
    })
}

fn cached_index(rows: IndexRows) -> PyResult<CachedIndex> {
    let (
        roots,
        resources,
        declarations,
        usages,
        grants,
        visibility,
        inaccessible,
        diagnostics,
        done,
    ) = rows;
    let mut index: CachedIndex = CachedIndex {
        completeness: [done.0, done.1, done.2, done.3, done.4, done.5],
        ..CachedIndex::default()
    };
    for row in roots {
        index.roots.push(ownership_root(row)?);
    }
    for row in resources {
        index.resources.push(resource_record(row)?);
    }
    for row in declarations {
        index.declarations.push(full_declaration(row)?);
    }
    for (consumer, declaration, kind, through, enum_member) in usages {
        index.usages.push(CachedUsage {
            consumer: qualified_identity(consumer)?,
            declaration: declaration_identity(declaration)?,
            kind,
            through: optional_identity(through)?,
            enum_member,
        });
    }
    for (resource, declaration, through, kind) in grants {
        index.grants.push(ReportGrant {
            resource: resource_identity(resource)?,
            declaration: declaration_identity(declaration)?,
            through: qualified_identity(through)?,
            kind: grant_kind(&kind)?,
        });
    }
    for (resource, declaration, reason, through) in visibility {
        index.visibility.push(CachedVisibility {
            resource: resource_identity(resource)?,
            declaration: declaration_identity(declaration)?,
            reason,
            through: optional_identity(through)?,
        });
    }
    for (resource, declaration, reason) in inaccessible {
        index.inaccessible.push(CachedInaccessible {
            resource: resource_identity(resource)?,
            declaration: declaration_identity(declaration)?,
            reason,
        });
    }
    for (code, message, severity, path, line, column, declaration, resource) in diagnostics {
        index.diagnostics.push(CachedDiagnostic {
            code,
            message,
            severity,
            path,
            line,
            column,
            declaration: declaration.map(declaration_identity).transpose()?,
            resource: resource.map(resource_identity).transpose()?,
        });
    }
    Ok(index)
}

fn identity_row(identity: &ResourceIdentity) -> IdentityRow {
    (identity.kind.as_str().to_owned(), identity.name.clone())
}

fn declaration_row(identity: &DeclarationIdentity) -> QualifiedRow {
    (
        identity.kind.as_str().to_owned(),
        identity.name.clone(),
        identity.owner.as_ref().map(identity_row),
    )
}

fn qualified_row(identity: &QualifiedIdentity) -> QualifiedRow {
    match identity {
        QualifiedIdentity::Resource(identity) => (
            identity.kind.as_str().to_owned(),
            identity.name.clone(),
            None,
        ),
        QualifiedIdentity::Declaration(identity) => declaration_row(identity),
    }
}

fn root_row(root: &OwnershipRoot) -> RootRow {
    (
        root.path.clone(),
        root.kind.as_str().to_owned(),
        root.resource_kind
            .map(|kind| ResourceKind::as_str(kind).to_owned()),
    )
}

fn resource_row(record: &ResourceRecord) -> ResourceRow {
    (
        identity_row(&record.identity),
        record.path.clone(),
        root_row(&record.ownership_root),
    )
}

fn record_row(record: &DeclarationRecord) -> DeclarationRow {
    (
        declaration_row(&record.identity),
        record.path.clone(),
        record.line,
        record.column,
        record.scope.as_str().to_owned(),
        root_row(&record.ownership_root),
        record.owning_path.clone(),
    )
}

fn full_declaration_row(item: &CachedDeclaration) -> FullDeclarationRow {
    (
        record_row(&item.record),
        item.macro_facts.as_ref().map(|facts| {
            (
                facts.parameters.clone(),
                facts.dependencies.iter().map(declaration_row).collect(),
                facts.source_digest.clone(),
            )
        }),
        item.enum_facts
            .as_ref()
            .map(|facts| (facts.members.clone(), facts.scalar_type.clone())),
        item.constant_facts.as_ref().map(|facts| {
            (
                facts.logical_type.clone(),
                facts.collection_kind.clone(),
                facts.item_count,
                facts.nullable,
                facts.render_as.clone(),
            )
        }),
    )
}

fn index_rows(index: &CachedIndex) -> IndexRows {
    let done: [bool; 6] = index.completeness;
    (
        index.roots.iter().map(root_row).collect(),
        index.resources.iter().map(resource_row).collect(),
        index
            .declarations
            .iter()
            .map(full_declaration_row)
            .collect(),
        index
            .usages
            .iter()
            .map(|item| {
                (
                    qualified_row(&item.consumer),
                    declaration_row(&item.declaration),
                    item.kind.clone(),
                    item.through.as_ref().map(qualified_row),
                    item.enum_member.clone(),
                )
            })
            .collect(),
        index
            .grants
            .iter()
            .map(|item| {
                (
                    identity_row(&item.resource),
                    declaration_row(&item.declaration),
                    qualified_row(&item.through),
                    item.kind.as_str().to_owned(),
                )
            })
            .collect(),
        index
            .visibility
            .iter()
            .map(|item| {
                (
                    identity_row(&item.resource),
                    declaration_row(&item.declaration),
                    item.reason.clone(),
                    item.through.as_ref().map(qualified_row),
                )
            })
            .collect(),
        index
            .inaccessible
            .iter()
            .map(|item| {
                (
                    identity_row(&item.resource),
                    declaration_row(&item.declaration),
                    item.reason.clone(),
                )
            })
            .collect(),
        index
            .diagnostics
            .iter()
            .map(|item| {
                (
                    item.code.clone(),
                    item.message.clone(),
                    item.severity.clone(),
                    item.path.clone(),
                    item.line,
                    item.column,
                    item.declaration.as_ref().map(declaration_row),
                    item.resource.as_ref().map(identity_row),
                )
            })
            .collect(),
        (done[0], done[1], done[2], done[3], done[4], done[5]),
    )
}

/// The scope index fingerprint of `project_dir`, `None` when it cannot be read.
#[pyfunction]
fn scope_index_fingerprint(
    py: Python<'_>,
    project_dir: PathBuf,
    inputs: FingerprintRow,
) -> PyResult<Option<String>> {
    let (config_files, roots, declaration_directories, named_declaration_directories, version) =
        inputs;
    let inputs: FingerprintInputs = FingerprintInputs {
        config_files,
        roots,
        declaration_directories,
        named_declaration_directories,
        sqlbuild_version: version,
    };
    let fingerprint: Fingerprint = py
        .compiler_detach(|| Ok(scope_fingerprint(&project_dir, &inputs)))
        .map_err(compiler_error)?;
    match fingerprint {
        Fingerprint::Hash(hash) => Ok(Some(hash)),
        Fingerprint::Unavailable => Ok(None),
        Fingerprint::Unserializable => Err(PyTypeError::new_err(
            "a scope-relevant config value is not JSON serializable",
        )),
    }
}

/// The verified cached index rows at `path` for `fingerprint`, else `None`.
#[pyfunction]
fn read_scope_index_cache(
    py: Python<'_>,
    path: PathBuf,
    fingerprint: String,
) -> PyResult<Option<IndexRows>> {
    let cached = py
        .compiler_detach(|| Ok(read_scope_cache(&path, &fingerprint)))
        .map_err(compiler_error)?;
    Ok(match cached {
        Ok(index) => Some(index_rows(&index)),
        Err(_) => None,
    })
}

/// Atomically write the canonical index `rows` for `fingerprint`; whether the write landed.
#[pyfunction]
fn write_scope_index_cache(
    py: Python<'_>,
    location: (PathBuf, String),
    fingerprint: String,
    rows: IndexRows,
) -> PyResult<bool> {
    let index: CachedIndex = cached_index(rows)?;
    let (directory, file_name) = location;
    py.compiler_detach(|| {
        Ok(match encode_scope_cache(&index, &fingerprint) {
            Ok(envelope) => matches!(write_scope_cache(&directory, &file_name, &envelope), Ok(())),
            Err(_) => false,
        })
    })
    .map_err(compiler_error)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scope_index_fingerprint, module)?)?;
    module.add_function(wrap_pyfunction!(read_scope_index_cache, module)?)?;
    module.add_function(wrap_pyfunction!(write_scope_index_cache, module)?)?;
    Ok(())
}
