//! Native declaration scopes as the plain rows the Python scope facade materialises.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{IntoPyObject, pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_scopes::scope_index::main::build_scope_index::build_scope_index;
use sqlbuild_scopes::scope_index::main::relationship_grants::relationship_grants;
use sqlbuild_scopes::scope_index::models::{
    DeclarationIdentity, DeclarationInput, DeclarationRecord, GrantRecord, GrantThrough,
    RelationshipFact, ResourceIdentity, ResourceInput, ScopeDeferral, ScopeDiagnostic, ScopeIndex,
    ScopeInputs,
};
use sqlbuild_scopes::scope_index::models::{
    DeclarationKind, ResourceKind, ResourceRoot, ScopeKind,
};

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::scopes::relationship_scan::{
    RelationshipScanSettings, ScenarioRow, TestFileRow, scanned_relationships,
};
use crate::bindings::types::CompilerDetach;
use sqlbuild_scopes::relationship_names::models::RelationshipScan;

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
/// The grants, or `None` when the index cannot place them, and each `(path, message)` fault.
type GrantedRelationships = (Option<Vec<GrantRow>>, Vec<(String, String)>);

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

    /// Read every test's and scenario's relationship facts, then resolve and keep their grants.
    fn grant_relationships(
        &mut self,
        py: Python<'_>,
        files: Vec<TestFileRow>,
        scenarios: Vec<ScenarioRow>,
        settings: RelationshipScanSettings,
    ) -> PyResult<GrantedRelationships> {
        let scan: RelationshipScan = scanned_relationships(py, &files, &scenarios, settings)?;
        let index: &ScopeIndex = &self.index;
        let facts: &[RelationshipFact] = &scan.facts;
        let grants: Result<Vec<GrantRecord>, ScopeDeferral> = py
            .compiler_detach(|| Ok(relationship_grants(index, facts)))
            .map_err(compiler_error)?;
        let Ok(grants) = grants else {
            return Ok((None, scan.faults));
        };
        let rows: Vec<GrantRow> = grants.iter().map(grant_row).collect();
        self.grants = grants;
        Ok((Some(rows), scan.faults))
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

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeScopeIndex>()?;
    module.add_function(wrap_pyfunction!(build_native_scope_index, module)?)?;
    Ok(())
}
