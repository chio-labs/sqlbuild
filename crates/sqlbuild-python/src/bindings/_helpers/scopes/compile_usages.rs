//! Compile usage facts: schema parent and enum usages with S006, and the usage merge.

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_scopes::compile_usages::main::distinct_positions::distinct_positions;
use sqlbuild_scopes::compile_usages::main::merged_dependencies::merged_dependencies;
use sqlbuild_scopes::compile_usages::main::schema_scope_usages::schema_scope_usages;
use sqlbuild_scopes::compile_usages::models::{
    DependencySource, InaccessibleDiagnostic, NamedRecord, SchemaDeclaration, SchemaUsages,
};
use sqlbuild_scopes::scope_index::models::{
    DeclarationKind, DeclaredScope, ResourceIdentity, ResourceKind, ScopeKind,
};

use crate::bindings::_helpers::compiled_project::model_loop_named::scope_path_message;

type IdentityRow = (String, String);
/// A declaration's kind, name and private owner; a resource's kind and name with no owner.
type QualifiedRow = (String, String, Option<IdentityRow>);
/// Consumer, declaration, usage kind, what it is used through, and the enum member.
type UsageRow = (
    QualifiedRow,
    QualifiedRow,
    String,
    Option<QualifiedRow>,
    Option<String>,
);
/// Path, scope, private owner, owning path and ownership root path of a named record.
type RecordRow = (String, String, Option<IdentityRow>, Option<String>, String);
/// Name, the schema it extends, and each column's name and type.
type SchemaRow = (String, Option<String>, Vec<(String, Option<String>)>);
/// Report key, message, path and help of one S006.
type DiagnosticRow = (Vec<String>, String, String, String);
/// Usages as `(consumer, declaration)` record positions, S006s, else a scope path error.
type SchemaUsageRows = (Vec<(usize, usize)>, Vec<DiagnosticRow>, Option<String>);
/// `(own, position)`: an own dependency's position, else a distinct usage's.
type SourceRow = (bool, usize);
/// Distinct collected positions, merged sources per declaration, and final usage positions.
type MergeRows = (Vec<usize>, Vec<Option<Vec<SourceRow>>>, Vec<usize>);

fn invalid(what: &str) -> pyo3::PyErr {
    PyValueError::new_err(format!("invalid compile usage {what}"))
}

fn named_record(handle: usize, row: RecordRow) -> PyResult<NamedRecord> {
    let (path, scope, owner, owning_path, ownership_root) = row;
    let owner: Option<ResourceIdentity> = match owner {
        None => None,
        Some((kind, name)) => Some(ResourceIdentity {
            kind: ResourceKind::parse(&kind).ok_or_else(|| invalid("owner kind"))?,
            name,
        }),
    };
    Ok(NamedRecord {
        handle,
        path,
        declared: DeclaredScope {
            scope: ScopeKind::parse(&scope).ok_or_else(|| invalid("scope"))?,
            owner,
            owning_path,
        },
        ownership_root,
    })
}

fn diagnostic_row(diagnostic: InaccessibleDiagnostic) -> DiagnosticRow {
    (
        diagnostic.key,
        diagnostic.message,
        diagnostic.path,
        diagnostic.help,
    )
}

/// Each schema's parent and enum usages over `records` by `(kind, name)` handle, with S006s.
#[pyfunction]
fn scope_schema_usages(
    schemas: Vec<SchemaRow>,
    records: Vec<(IdentityRow, RecordRow)>,
) -> PyResult<SchemaUsageRows> {
    let mut schema_records: HashMap<String, NamedRecord> = HashMap::new();
    let mut enum_records: HashMap<String, NamedRecord> = HashMap::new();
    for (handle, ((kind, name), row)) in records.into_iter().enumerate() {
        let target: &mut HashMap<String, NamedRecord> =
            match DeclarationKind::parse(&kind).ok_or_else(|| invalid("declaration kind"))? {
                DeclarationKind::Schema => &mut schema_records,
                DeclarationKind::Enum => &mut enum_records,
                _ => continue,
            };
        target.insert(name, named_record(handle, row)?);
    }
    let mut declarations: Vec<SchemaDeclaration> = Vec::with_capacity(schemas.len());
    for (name, extends, columns) in schemas {
        declarations.push(SchemaDeclaration {
            name,
            extends,
            columns,
        });
    }
    Ok(
        match schema_scope_usages(&declarations, &schema_records, &enum_records) {
            Ok(SchemaUsages {
                usages,
                diagnostics,
            }) => (
                usages,
                diagnostics.into_iter().map(diagnostic_row).collect(),
                None,
            ),
            Err(rejected) => (
                Vec::new(),
                Vec::new(),
                Some(scope_path_message(&rejected.declared, &rejected.path)),
            ),
        },
    )
}

fn source_row(source: DependencySource) -> SourceRow {
    match source {
        DependencySource::Own(position) => (true, position),
        DependencySource::Usage(position) => (false, position),
    }
}

fn source_rows(sources: Option<Vec<DependencySource>>) -> Option<Vec<SourceRow>> {
    sources.map(|sources| sources.into_iter().map(source_row).collect())
}

/// Distinct collected usages, merged macro dependencies, and the distinct prior-then-new usages.
#[pyfunction]
fn scope_merged_usages(
    declarations: Vec<(QualifiedRow, Option<Vec<QualifiedRow>>)>,
    prior: Vec<UsageRow>,
    collected: Vec<UsageRow>,
) -> MergeRows {
    let distinct: Vec<usize> = distinct_positions(&collected);
    let mut consumed: Vec<(Option<QualifiedRow>, QualifiedRow)> =
        Vec::with_capacity(distinct.len());
    for position in &distinct {
        let (consumer, declaration, _, _, _) = &collected[*position];
        let by_declaration: Option<QualifiedRow> = DeclarationKind::parse(&consumer.0)
            .is_some()
            .then(|| consumer.clone());
        consumed.push((by_declaration, declaration.clone()));
    }
    let merged: Vec<Option<Vec<SourceRow>>> = merged_dependencies(&declarations, &consumed)
        .into_iter()
        .map(source_rows)
        .collect();
    let mut combined: Vec<&UsageRow> = prior.iter().collect();
    combined.extend(distinct.iter().map(|position| &collected[*position]));
    let combined_positions: Vec<usize> = distinct_positions(&combined);
    (distinct, merged, combined_positions)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(scope_schema_usages, module)?)?;
    module.add_function(wrap_pyfunction!(scope_merged_usages, module)?)?;
    Ok(())
}
