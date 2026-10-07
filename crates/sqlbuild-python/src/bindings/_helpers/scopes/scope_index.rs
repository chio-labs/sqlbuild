//! Native declaration scopes as the plain rows the Python scope facade materialises.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{IntoPyObject, pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_scopes::scope_index::main::build_scope_index::build_scope_index;
use sqlbuild_scopes::scope_index::main::relationship_grants::relationship_grants;
use sqlbuild_scopes::scope_index::main::scope_lookup::scope_lookup_groups;
use sqlbuild_scopes::scope_index::models::{
    DeclarationIdentity, DeclarationInput, DeclarationRecord, GrantRecord, GrantThrough,
    KeyedGroups, RelationshipFact, ResourceIdentity, ResourceInput, ScopeDeferral, ScopeDiagnostic,
    ScopeIndex, ScopeInputs, ScopeLookupGroups,
};
use sqlbuild_scopes::scope_index::models::{
    DeclarationKind, ResourceKind, ResourceRoot, ScopeKind,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::types::CompilerDetach;

type IdentityRow = (String, String);
type DeclarationIdentityRow = (String, String, Option<IdentityRow>);
type ResourceRow = (String, String, String, String);
type DeclarationRow = (
    String,
    String,
    Option<IdentityRow>,
    String,
    i64,
    String,
    Option<String>,
    String,
    Option<String>,
    Vec<DeclarationIdentityRow>,
);
type FactRow = (String, String, Vec<String>, Vec<String>, Vec<String>);
type DeclarationRecordRow = (
    String,
    String,
    &'static str,
    Option<&'static str>,
    Option<String>,
);
type DiagnosticRow = (
    &'static str,
    String,
    Option<String>,
    Option<i64>,
    Option<i64>,
    Option<usize>,
    Option<usize>,
);
type IndexRows = (
    Vec<String>,
    Vec<DeclarationRecordRow>,
    Vec<usize>,
    Vec<usize>,
    Vec<(usize, usize)>,
    Vec<DiagnosticRow>,
    bool,
);
type GrantRow = (&'static str, String, usize, ThroughRow, &'static str);
type GroupRows = (Vec<Vec<usize>>, bool);
type VisibilityRows = (
    Vec<usize>,
    Vec<(IdentityRow, Vec<usize>)>,
    Vec<(String, Vec<usize>)>,
    Vec<(String, Vec<usize>)>,
);
type LookupRows = (
    Vec<usize>,
    Vec<usize>,
    Vec<usize>,
    Vec<usize>,
    (
        GroupRows,
        GroupRows,
        GroupRows,
        GroupRows,
        GroupRows,
        GroupRows,
    ),
    VisibilityRows,
);

/// What a grant came through: an expected model's name or a tested macro's declaration index.
#[derive(IntoPyObject)]
enum ThroughRow {
    Model(String),
    Declaration(usize),
}

/// A built scope index held natively between the facade's index, grant and lookup steps.
#[pyclass(module = "sqlbuild._native")]
pub(crate) struct NativeScopeIndex {
    index: ScopeIndex,
    grants: Vec<GrantRecord>,
}

#[pymethods]
impl NativeScopeIndex {
    /// The index's records, builder orders, usages, diagnostics and relationship flag.
    fn records(&self) -> IndexRows {
        let index: &ScopeIndex = &self.index;
        (
            index
                .resources
                .iter()
                .map(|record| record.path.clone())
                .collect(),
            index.declarations.iter().map(declaration_row).collect(),
            index.resource_order.clone(),
            index.declaration_order.clone(),
            index
                .usages
                .iter()
                .map(|usage| (usage.consumer, usage.dependency))
                .collect(),
            index.diagnostics.iter().map(diagnostic_row).collect(),
            index.has_scoped_relationship_declarations,
        )
    }

    /// Resolve and keep the relationship grants of `facts`; `None` when Python must run.
    fn grant(&mut self, py: Python<'_>, facts: Vec<FactRow>) -> PyResult<Option<Vec<GrantRow>>> {
        let Some(facts) = facts
            .into_iter()
            .map(relationship_fact)
            .collect::<Option<Vec<RelationshipFact>>>()
        else {
            return Ok(None);
        };
        let index: &ScopeIndex = &self.index;
        let grants: Result<Vec<GrantRecord>, ScopeDeferral> = py
            .compiler_detach(|| Ok(relationship_grants(index, &facts)))
            .map_err(compiler_error)?;
        let Ok(grants) = grants else {
            return Ok(None);
        };
        let rows: Vec<GrantRow> = grants.iter().map(grant_row).collect();
        self.grants = grants;
        Ok(Some(rows))
    }

    /// The lookup orders and groups of the index with its kept grants; `None` when Python must run.
    fn lookup(&self, py: Python<'_>) -> PyResult<Option<LookupRows>> {
        let index: &ScopeIndex = &self.index;
        let grants: &[GrantRecord] = &self.grants;
        let groups: Result<ScopeLookupGroups, ScopeDeferral> = py
            .compiler_detach(|| Ok(scope_lookup_groups(index, grants)))
            .map_err(compiler_error)?;
        let Ok(groups) = groups else {
            return Ok(None);
        };
        Ok(Some((
            index.canonical_resources.clone(),
            index.canonical_declarations.clone(),
            groups.canonical_usages,
            groups.canonical_grants,
            (
                group_rows(groups.resources),
                group_rows(groups.resources_by_path),
                group_rows(groups.declarations),
                group_rows(groups.usages_by_consumer),
                group_rows(groups.usages_by_declaration),
                group_rows(groups.grants_by_resource),
            ),
            (
                groups.visibility.global,
                groups
                    .visibility
                    .private
                    .into_iter()
                    .map(|(owner, positions)| {
                        ((owner.kind.as_str().to_owned(), owner.name), positions)
                    })
                    .collect(),
                groups.visibility.local,
                groups.visibility.inherited,
            ),
        )))
    }
}

/// Build the static scope index natively, or return `None` when Python must build it.
#[pyfunction]
fn build_native_scope_index(
    py: Python<'_>,
    resources: Vec<ResourceRow>,
    declarations: Vec<DeclarationRow>,
) -> PyResult<Option<NativeScopeIndex>> {
    let Some(inputs) = scope_inputs(resources, declarations) else {
        return Ok(None);
    };
    let index: Result<ScopeIndex, ScopeDeferral> = py
        .compiler_detach(|| Ok(build_scope_index(inputs)))
        .map_err(compiler_error)?;
    match index {
        Ok(index) => Ok(Some(NativeScopeIndex {
            index,
            grants: Vec::new(),
        })),
        Err(_deferral) => Ok(None),
    }
}

fn scope_inputs(
    resources: Vec<ResourceRow>,
    declarations: Vec<DeclarationRow>,
) -> Option<ScopeInputs> {
    Some(ScopeInputs {
        resources: resources
            .into_iter()
            .map(|(kind, name, path, root)| {
                Some(ResourceInput {
                    identity: resource_identity((kind, name))?,
                    path,
                    root: match root.as_str() {
                        "kind" => ResourceRoot::Kind,
                        "seed" => ResourceRoot::Seed,
                        "python_function" => ResourceRoot::PythonFunction,
                        _ => return None,
                    },
                })
            })
            .collect::<Option<_>>()?,
        declarations: declarations
            .into_iter()
            .map(declaration_input)
            .collect::<Option<_>>()?,
    })
}

fn declaration_input(row: DeclarationRow) -> Option<DeclarationInput> {
    let (
        kind,
        name,
        owner,
        path,
        line,
        scope,
        ownership_root,
        root_fallback,
        owning_path,
        dependencies,
    ) = row;
    Some(DeclarationInput {
        identity: declaration_identity((kind, name, owner))?,
        path,
        line,
        scope: ScopeKind::parse(&scope)?,
        ownership_root,
        root_fallback,
        owning_path,
        dependencies: dependencies
            .into_iter()
            .map(declaration_identity)
            .collect::<Option<_>>()?,
    })
}

fn resource_identity((kind, name): IdentityRow) -> Option<ResourceIdentity> {
    Some(ResourceIdentity {
        kind: ResourceKind::parse(&kind)?,
        name,
    })
}

fn declaration_identity(
    (kind, name, owner): DeclarationIdentityRow,
) -> Option<DeclarationIdentity> {
    Some(DeclarationIdentity {
        kind: DeclarationKind::parse(&kind)?,
        name,
        owner: match owner {
            Some(owner) => Some(resource_identity(owner)?),
            None => None,
        },
    })
}

fn relationship_fact(
    (kind, name, expected_models, called_macros, tested_macros): FactRow,
) -> Option<RelationshipFact> {
    Some(RelationshipFact {
        resource: resource_identity((kind, name))?,
        expected_models,
        called_macros,
        tested_macros,
    })
}

fn declaration_row(record: &DeclarationRecord) -> DeclarationRecordRow {
    (
        record.path.clone(),
        record.ownership_root.path.clone(),
        record.ownership_root.kind.as_str(),
        record
            .ownership_root
            .resource_kind
            .map(ResourceKind::as_str),
        record.owning_path.clone(),
    )
}

fn diagnostic_row(diagnostic: &ScopeDiagnostic) -> DiagnosticRow {
    (
        diagnostic.code.as_str(),
        diagnostic.message.clone(),
        diagnostic.path.clone(),
        diagnostic.line,
        diagnostic.column,
        diagnostic.declaration,
        diagnostic.resource,
    )
}

fn grant_row(grant: &GrantRecord) -> GrantRow {
    (
        grant.resource.kind.as_str(),
        grant.resource.name.clone(),
        grant.declaration,
        match &grant.through {
            GrantThrough::Model(name) => ThroughRow::Model(name.clone()),
            GrantThrough::Declaration(declaration) => ThroughRow::Declaration(*declaration),
        },
        grant.kind.as_str(),
    )
}

fn group_rows(groups: KeyedGroups) -> GroupRows {
    (groups.groups, groups.repr_ordered)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeScopeIndex>()?;
    module.add_function(wrap_pyfunction!(build_native_scope_index, module)?)?;
    Ok(())
}
