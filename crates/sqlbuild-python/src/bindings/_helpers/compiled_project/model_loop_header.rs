//! A model's MODEL header attached as its schema entry, by the native header parser.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyString, PyStringMethods, PyTuple};
use sqlbuild_analysis::compiled_project::main::enum_typed_columns::enum_typed_columns;
use sqlbuild_analysis::compiled_project::main::header_attachment_feature::header_attachment_feature;
use sqlbuild_analysis::compiled_project::models::{
    HeaderColumnShape, ModelSchemaFact, SchemaColumnFact,
};
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_model_config::header_metadata::models::{ParsedAudit, ParsedColumn};
use sqlbuild_model_config::model_validation::models::ColumnMigration;

use crate::bindings::_helpers::compiled_project::model_loop::{
    LoopContext, compile_error, config_error,
};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::{config_keys, present};
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::column_migrations::column_migration_error;
use crate::bindings::_helpers::model_config::config_errors::native_config_error;
use crate::bindings::_helpers::model_config::header_metadata::{audit_tuple, column_tuple};

const DESCRIPTION_KEY: &str = "description";
const COLUMNS_KEY: &str = "columns";
const AUDITS_KEY: &str = "audits";
const STRIP_METHOD: &str = "strip";

/// What a model's header schema entry is attached from.
pub(crate) struct HeaderSource<'a, 'py> {
    pub(crate) name: &'a str,
    pub(crate) values: &'a Bound<'py, PyDict>,
    pub(crate) locations: &'a Bound<'py, PyDict>,
    pub(crate) relative_path: &'a str,
    pub(crate) enum_names: &'a [String],
}

/// The header's description and, when it declares description, columns or audits, its entry.
pub(crate) struct AttachedHeader<'py> {
    pub(crate) description: Option<String>,
    pub(crate) schema: Option<HeaderSchema<'py>>,
}

/// A header schema entry's Python columns and audits, type enforcement and retained fact.
pub(crate) struct HeaderSchema<'py> {
    pub(crate) columns: Bound<'py, PyTuple>,
    pub(crate) audits: Bound<'py, PyTuple>,
    pub(crate) type_enforcement: bool,
    pub(crate) fact: ModelSchemaFact,
}

/// The attached header, raising the attachment's errors; `None` for a feature it still finishes.
pub(crate) fn header_schema<'py>(
    py: Python<'py>,
    context: &LoopContext<'_, 'py>,
    source: &HeaderSource<'_, 'py>,
) -> PyResult<Option<AttachedHeader<'py>>> {
    let description: Option<String> = description(context, source)?;
    if header_attachment_feature(&config_keys(source.values)?).is_some() {
        return Ok(None);
    }
    let columns: Option<Bound<'py, PyAny>> = present(source.values, COLUMNS_KEY)?;
    let audits: Option<Bound<'py, PyAny>> = present(source.values, AUDITS_KEY)?;
    if description.is_none() && columns.is_none() && audits.is_none() {
        return Ok(Some(AttachedHeader {
            description,
            schema: None,
        }));
    }
    let none: Bound<'py, PyAny> = py.None().into_bound(py);
    let columns_node: PyNode<'py> = PyNode(columns.unwrap_or_else(|| none.clone()));
    let audits_node: PyNode<'py> = PyNode(audits.unwrap_or(none));
    let metadata = parse_header_metadata(&columns_node, &audits_node, source.relative_path);
    let parsed_columns = metadata
        .columns
        .map_err(|error| raised_config_error(py, context, error))?;
    let parsed_audits = metadata
        .audits
        .map_err(|error| raised_config_error(py, context, error))?;
    let migrations: Vec<ColumnMigration> = parsed_columns
        .iter()
        .map(column_migration)
        .collect::<PyResult<_>>()?;
    if let Some(error) = column_migration_error(source.name, source.values, &migrations)? {
        let error = native_config_error(py, error)?.into_bound(py).into_any();
        return Err(config_error(context.classes, &error, Some(source.values)));
    }
    let shapes: Vec<HeaderColumnShape> = parsed_columns
        .iter()
        .map(column_shape)
        .collect::<PyResult<_>>()?;
    if enum_typed_columns(&shapes, source.enum_names) {
        return Ok(None);
    }
    Ok(Some(AttachedHeader {
        description,
        schema: Some(HeaderSchema {
            columns: column_tuple(py, context.contracts, &parsed_columns, source.locations)?,
            audits: audit_tuple(py, context.contracts, &parsed_audits)?,
            type_enforcement: shapes.iter().any(|shape| shape.column_type.is_some()),
            fact: schema_fact(&parsed_columns, &parsed_audits)?,
        }),
    }))
}

/// The header description: absent, or a non-blank string by Python's `str.strip`.
fn description(
    context: &LoopContext<'_, '_>,
    source: &HeaderSource<'_, '_>,
) -> PyResult<Option<String>> {
    let Some(value) = present(source.values, DESCRIPTION_KEY)? else {
        return Ok(None);
    };
    if let Ok(text) = value.downcast::<PyString>()
        && text.call_method0(STRIP_METHOD)?.is_truthy()?
    {
        return Ok(Some(text.to_str()?.to_owned()));
    }
    let message: String = format!(
        "{} model '{DESCRIPTION_KEY}' must be a non-empty string",
        source.relative_path
    );
    Err(compile_error(context.classes, &message, None))
}

fn raised_config_error(
    py: Python<'_>,
    context: &LoopContext<'_, '_>,
    error: sqlbuild_model_config::errors::ConfigError,
) -> pyo3::PyErr {
    match native_config_error(py, error) {
        Ok(native) => config_error(context.classes, native.bind(py).as_any(), None),
        Err(failure) => failure,
    }
}

fn schema_fact(
    columns: &[ParsedColumn<PyNode<'_>>],
    audits: &[ParsedAudit<PyNode<'_>>],
) -> PyResult<ModelSchemaFact> {
    Ok(ModelSchemaFact {
        audit_count: u32::try_from(audits.len()).unwrap_or(u32::MAX),
        columns: columns.iter().map(column_fact).collect::<PyResult<_>>()?,
        dynamic_columns: Vec::new(),
    })
}

fn column_fact(column: &ParsedColumn<PyNode<'_>>) -> PyResult<SchemaColumnFact> {
    Ok(SchemaColumnFact {
        name: column.name.0.str()?.to_string(),
        data_type: optional_text(column.column_type.as_ref())?,
        nullable: match &column.nullable {
            Some(node) if !node.0.is_none() => Some(node.0.is_truthy()?),
            _ => None,
        },
        audit_count: u32::try_from(column.audits.len()).unwrap_or(u32::MAX),
    })
}

fn column_shape(column: &ParsedColumn<PyNode<'_>>) -> PyResult<HeaderColumnShape> {
    Ok(HeaderColumnShape {
        column_type: optional_text(column.column_type.as_ref())?,
    })
}

fn column_migration(column: &ParsedColumn<PyNode<'_>>) -> PyResult<ColumnMigration> {
    Ok(ColumnMigration {
        name: column.name.0.str()?.to_string(),
        migrate_from: optional_text(column.migrate_from.as_ref())?,
    })
}

fn optional_text(node: Option<&PyNode<'_>>) -> PyResult<Option<String>> {
    match node {
        Some(node) if !node.0.is_none() => Ok(Some(node.0.str()?.to_string())),
        _ => Ok(None),
    }
}
