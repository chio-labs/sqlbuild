//! Compile usage facts: schema parent and enum usages with S006, and the usage merge.

use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
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

use crate::bindings::_helpers::compile_driver::diagnostic_collector::report_compile_diagnostic;
use crate::bindings::_helpers::compiled_project::model_loop_named::scope_path_message;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::construct::new_record;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_items;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};

const INACCESSIBLE_DECLARATION_CODE: &str = "S006";
const SCHEMA_USAGE_KINDS: [&str; 2] = ["schema", "enum"];

type IdentityRow = (String, String);
/// A declaration's kind, name and private owner; a resource's kind and name with no owner.
type QualifiedRow = (String, String, Option<IdentityRow>);
/// Consumer, declaration, usage kind, what it is used through, and the enum member.
pub(crate) type UsageRow = (
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
pub(crate) type SourceRow = (bool, usize);
/// Distinct collected positions, merged sources per declaration, and final usage positions.
pub(crate) type MergeRows = (Vec<usize>, Vec<Option<Vec<SourceRow>>>, Vec<usize>);

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

/// `model_schema_scope_usages`: each schema's parent and enum `UsageRecord`s; S006s are reported.
#[pyfunction]
pub(crate) fn model_schema_scope_usages<'py>(
    schema_files: &Bound<'py, PyAny>,
    resolver: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = schema_files.py();
    if resolver.is_none() {
        return Ok(PyTuple::empty(py));
    }
    let mut records: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut record_rows: Vec<(IdentityRow, RecordRow)> = Vec::new();
    let declarations = native_field(&native_field(resolver, "lookup")?, "declarations")?;
    for item in mapping_items(&declarations)?.try_iter()? {
        let (identity, found): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        if !found.is_truthy()?
            || !native_field(&identity, "owner")?.is_none()
            || !SCHEMA_USAGE_KINDS.contains(
                &native_field(&native_field(&identity, "kind")?, "value")?
                    .extract::<String>()?
                    .as_str(),
            )
        {
            continue;
        }
        let record: Bound<'py, PyAny> = found.get_item(0)?;
        let recorded: Bound<'py, PyAny> = native_field(&record, "identity")?;
        record_rows.push((
            (
                native_field(&native_field(&recorded, "kind")?, "value")?.extract()?,
                native_field(&recorded, "name")?.extract()?,
            ),
            record_row(&record)?,
        ));
        records.push(record);
    }
    let mut schemas: Vec<SchemaRow> = Vec::new();
    for file in schema_files.try_iter()? {
        for declaration in native_field(&file?, "declarations")?.try_iter()? {
            let declaration: Bound<'py, PyAny> = declaration?;
            let mut columns: Vec<(String, Option<String>)> = Vec::new();
            for column in native_field(&declaration, "columns")?.try_iter()? {
                let column: Bound<'py, PyAny> = column?;
                columns.push((
                    native_field(&column, "name")?.extract()?,
                    native_field(&column, "type")?.extract()?,
                ));
            }
            schemas.push((
                native_field(&declaration, "name")?.extract()?,
                native_field(&declaration, "extends")?.extract()?,
                columns,
            ));
        }
    }
    let (usages, diagnostics, error) = scope_schema_usages(schemas, record_rows)?;
    if let Some(message) = error {
        return Err(PyErr::from_value(
            error_class(py, ErrorId::InvalidScopePath)?.call1((message,))?,
        ));
    }
    report_inaccessible(py, diagnostics)?;
    let mut built: Vec<Bound<'py, PyAny>> = Vec::with_capacity(usages.len());
    for (consumer, used) in usages {
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        fields.set_item("consumer", native_field(&records[consumer], "identity")?)?;
        fields.set_item("declaration", native_field(&records[used], "identity")?)?;
        built.push(new_record(py, RecordId::UsageRecord, (), Some(&fields))?);
    }
    PyTuple::new(py, built)
}

/// A declaration record's path, scope, private owner, owning path and ownership root path.
fn record_row(record: &Bound<'_, PyAny>) -> PyResult<RecordRow> {
    let identity: Bound<'_, PyAny> = native_field(record, "identity")?;
    let owner: Bound<'_, PyAny> = native_field(&identity, "owner")?;
    Ok((
        native_field(record, "path")?.extract()?,
        native_field(&native_field(record, "scope")?, "value")?.extract()?,
        if owner.is_none() {
            None
        } else {
            Some((
                native_field(&native_field(&owner, "kind")?, "value")?.extract()?,
                native_field(&owner, "name")?.extract()?,
            ))
        },
        native_field(record, "owning_path")?.extract()?,
        native_field(&native_field(record, "ownership_root")?, "path")?.extract()?,
    ))
}

/// Report each S006 through the active compile diagnostic collector.
fn report_inaccessible(py: Python<'_>, diagnostics: Vec<DiagnosticRow>) -> PyResult<()> {
    if diagnostics.is_empty() {
        return Ok(());
    }
    let path_class = py.import("pathlib")?.getattr("Path")?;
    for (key, message, path, help) in diagnostics {
        let fields: Bound<'_, PyDict> = PyDict::new(py);
        fields.set_item("phase", "compile")?;
        fields.set_item("severity", "error")?;
        fields.set_item("code", INACCESSIBLE_DECLARATION_CODE)?;
        fields.set_item("message", message)?;
        fields.set_item("path", path_class.call1((path,))?)?;
        fields.set_item("help", help)?;
        report_compile_diagnostic(
            PyTuple::new(py, key)?.as_any(),
            &new_record(py, RecordId::CompilerDiagnostic, (), Some(&fields))?,
        )?;
    }
    Ok(())
}

/// Each schema's parent and enum usages over `records` by `(kind, name)` handle, with S006s.
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
pub(crate) fn merged_usage_rows(
    declarations: &[(QualifiedRow, Option<Vec<QualifiedRow>>)],
    prior: &[UsageRow],
    collected: &[UsageRow],
) -> MergeRows {
    let distinct: Vec<usize> = distinct_positions(collected);
    let mut consumed: Vec<(Option<QualifiedRow>, QualifiedRow)> =
        Vec::with_capacity(distinct.len());
    for position in &distinct {
        let (consumer, declaration, _, _, _) = &collected[*position];
        let by_declaration: Option<QualifiedRow> = DeclarationKind::parse(&consumer.0)
            .is_some()
            .then(|| consumer.clone());
        consumed.push((by_declaration, declaration.clone()));
    }
    let merged: Vec<Option<Vec<SourceRow>>> = merged_dependencies(declarations, &consumed)
        .into_iter()
        .map(source_rows)
        .collect();
    let mut combined: Vec<&UsageRow> = prior.iter().collect();
    combined.extend(distinct.iter().map(|position| &collected[*position]));
    let combined_positions: Vec<usize> = distinct_positions(&combined);
    (distinct, merged, combined_positions)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(model_schema_scope_usages, module)?)?;
    Ok(())
}
