//! Unused-declaration and exact-placement rules over a usage-complete scope index's rows.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_scopes::placement::main::declaration_directory::declaration_directory;
use sqlbuild_scopes::placement::main::placement_diagnostics::placement_diagnostics;
use sqlbuild_scopes::placement::main::relocate_for_resource_move::relocate_for_resource_move;
use sqlbuild_scopes::placement::models::{
    PlacementDiagnostic, PlacementIndex, PlacementUsage, Relocation,
};
use sqlbuild_scopes::scope_index::models::{
    DeclarationIdentity, DeclarationKind, DeclarationRecord, OwnershipRoot, OwnershipRootKind,
    QualifiedIdentity, ResourceIdentity, ResourceKind, ResourceRecord, ScopeKind,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

pub(crate) type IdentityRow = (String, String);
/// A declaration's kind, name and private owner; a resource's kind and name with no owner.
pub(crate) type QualifiedRow = (String, String, Option<IdentityRow>);
/// An ownership root's path, kind and resource kind.
pub(crate) type RootRow = (String, String, Option<String>);
pub(crate) type ResourceRow = (IdentityRow, String, RootRow);
/// Identity, path, line, column, scope, ownership root and owning path.
pub(crate) type DeclarationRow = (
    QualifiedRow,
    String,
    i64,
    i64,
    String,
    RootRow,
    Option<String>,
);
/// Consumer, declaration and what the consumer uses it through.
type UsageRow = (QualifiedRow, QualifiedRow, Option<QualifiedRow>);
type IndexRows = (Vec<ResourceRow>, Vec<DeclarationRow>, Vec<UsageRow>);
/// Declaration position, path, scope, ownership root and owning path.
type RelocationRow = (usize, String, &'static str, RootOut, Option<String>);
type RootOut = (String, &'static str, Option<&'static str>);

fn invalid(what: &str) -> pyo3::PyErr {
    PyValueError::new_err(format!("invalid scope placement {what}"))
}

pub(crate) fn resource_identity((kind, name): IdentityRow) -> PyResult<ResourceIdentity> {
    Ok(ResourceIdentity {
        kind: ResourceKind::parse(&kind).ok_or_else(|| invalid("resource kind"))?,
        name,
    })
}

pub(crate) fn declaration_identity(
    (kind, name, owner): QualifiedRow,
) -> PyResult<DeclarationIdentity> {
    Ok(DeclarationIdentity {
        kind: DeclarationKind::parse(&kind).ok_or_else(|| invalid("declaration kind"))?,
        name,
        owner: owner.map(resource_identity).transpose()?,
    })
}

/// Resource and declaration kinds share no values, so the kind tells the identities apart.
pub(crate) fn qualified_identity(row: QualifiedRow) -> PyResult<QualifiedIdentity> {
    if row.2.is_none()
        && let Some(kind) = ResourceKind::parse(&row.0)
    {
        return Ok(QualifiedIdentity::Resource(ResourceIdentity {
            kind,
            name: row.1,
        }));
    }
    Ok(QualifiedIdentity::Declaration(declaration_identity(row)?))
}

pub(crate) fn ownership_root((path, kind, resource_kind): RootRow) -> PyResult<OwnershipRoot> {
    Ok(OwnershipRoot {
        path,
        kind: OwnershipRootKind::parse(&kind).ok_or_else(|| invalid("root kind"))?,
        resource_kind: resource_kind
            .map(|kind| ResourceKind::parse(&kind).ok_or_else(|| invalid("resource kind")))
            .transpose()?,
    })
}

fn root_out(root: &OwnershipRoot) -> RootOut {
    (
        root.path.clone(),
        root.kind.as_str(),
        root.resource_kind.map(ResourceKind::as_str),
    )
}

fn relocation_row(item: Relocation) -> RelocationRow {
    (
        item.declaration,
        item.path,
        item.scope.as_str(),
        root_out(&item.ownership_root),
        item.owning_path,
    )
}

pub(crate) fn scope_kind(value: &str) -> PyResult<ScopeKind> {
    ScopeKind::parse(value).ok_or_else(|| invalid("scope"))
}

/// A resource row as its record.
pub(crate) fn resource_record((identity, path, root): ResourceRow) -> PyResult<ResourceRecord> {
    Ok(ResourceRecord {
        identity: resource_identity(identity)?,
        path,
        ownership_root: ownership_root(root)?,
    })
}

/// A declaration row as its record, without macro dependencies.
pub(crate) fn declaration_record(row: DeclarationRow) -> PyResult<DeclarationRecord> {
    let (identity, path, line, column, scope, root, owning_path) = row;
    Ok(DeclarationRecord {
        identity: declaration_identity(identity)?,
        path,
        line,
        column,
        scope: scope_kind(&scope)?,
        ownership_root: ownership_root(root)?,
        owning_path,
        dependencies: Vec::new(),
    })
}

fn placement_index((resources, declarations, usages): IndexRows) -> PyResult<PlacementIndex> {
    let mut index: PlacementIndex = PlacementIndex::default();
    for row in resources {
        index.resources.push(resource_record(row)?);
    }
    for row in declarations {
        index.declarations.push(declaration_record(row)?);
    }
    for (consumer, declaration, through) in usages {
        index.usages.push(PlacementUsage {
            consumer: qualified_identity(consumer)?,
            declaration: declaration_identity(declaration)?,
            through: through.map(qualified_identity).transpose()?,
        });
    }
    Ok(index)
}

/// Each `(declaration position, code, message)` placement diagnostic, in declaration order.
#[pyfunction]
fn scope_placement_diagnostics(
    py: Python<'_>,
    rows: IndexRows,
) -> PyResult<Vec<(usize, &'static str, String)>> {
    let index: PlacementIndex = placement_index(rows)?;
    let diagnostics: Vec<PlacementDiagnostic> = py
        .compiler_detach(|| Ok(placement_diagnostics(&index)))
        .map_err(compiler_error)?;
    Ok(diagnostics
        .into_iter()
        .map(|item| (item.declaration, item.code.as_str(), item.message))
        .collect())
}

/// Each declaration that moves when `resource` moves to `destination`, or `None` if unsettled.
#[pyfunction]
fn scope_relocations(
    py: Python<'_>,
    rows: IndexRows,
    resource: IdentityRow,
    destination: &str,
) -> PyResult<Option<Vec<RelocationRow>>> {
    let index: PlacementIndex = placement_index(rows)?;
    let resource: ResourceIdentity = resource_identity(resource)?;
    let relocations: Option<Vec<Relocation>> = py
        .compiler_detach(|| Ok(relocate_for_resource_move(&index, &resource, destination)))
        .map_err(compiler_error)?;
    Ok(relocations.map(|items| items.into_iter().map(relocation_row).collect()))
}

/// The project-relative folder where a declaration of `kind` with this placement lives.
#[pyfunction]
fn scope_declaration_directory(kind: &str, scope: &str, path: Option<&str>) -> PyResult<String> {
    let kind: DeclarationKind =
        DeclarationKind::parse(kind).ok_or_else(|| invalid("declaration kind"))?;
    Ok(declaration_directory(kind, scope_kind(scope)?, path))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scope_placement_diagnostics, module)?)?;
    module.add_function(wrap_pyfunction!(scope_relocations, module)?)?;
    module.add_function(wrap_pyfunction!(scope_declaration_directory, module)?)?;
    Ok(())
}
