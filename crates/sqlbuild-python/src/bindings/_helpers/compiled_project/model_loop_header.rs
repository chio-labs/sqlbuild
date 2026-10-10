//! A model's MODEL header attached as its schema entry, by the native header parser.

use std::cell::RefCell;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods, PyTuple, PyTupleMethods};
use sqlbuild_analysis::compiled_project::models::ModelSchemaFact;
use sqlbuild_model_config::header_metadata::main::audit_factory_references::audit_factory_references;
use sqlbuild_model_config::header_metadata::main::merged_audit_identities::merged_audit_identities;
use sqlbuild_model_config::header_metadata::main::parse_dynamic_columns::parse_dynamic_columns;
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_model_config::header_metadata::models::{DynamicFamily, ParsedColumn};
use sqlbuild_model_config::model_validation::models::ColumnMigration;

use crate::bindings::_helpers::compiled_project::model_loop::{
    LoopContext, compile_error, config_error,
};
use crate::bindings::_helpers::compiled_project::model_loop_contracts::{
    EnumColumns, audit_identity, dynamic_family_objects, enum_columns, factory_audits, schema_row,
};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::present;
use crate::bindings::_helpers::compiled_project::project::schema_fact;
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::column_migrations::column_migration_error;
use crate::bindings::_helpers::model_config::config_errors::native_config_error;
use crate::bindings::_helpers::model_config::header_metadata::{audit_tuple, column_tuple};

const DESCRIPTION_KEY: &str = "description";
const COLUMNS_KEY: &str = "columns";
const AUDITS_KEY: &str = "audits";
const DYNAMIC_COLUMNS_KEY: &str = "dynamic_columns";
const AUDIT_FACTORIES_KEY: &str = "audit_factories";
const RE_MODULE: &str = "re";
const COMPILE_FUNCTION: &str = "compile";
const ERROR_CLASS: &str = "error";
const STRIP_METHOD: &str = "strip";

/// What a model's header schema entry is attached from.
pub(crate) struct HeaderSource<'a, 'py> {
    pub(crate) name: &'a str,
    pub(crate) values: &'a Bound<'py, PyDict>,
    pub(crate) locations: &'a Bound<'py, PyDict>,
    pub(crate) relative_path: &'a str,
    /// The model's visible declarations and the identity its usages are recorded for.
    pub(crate) visible: (&'a Bound<'py, PyAny>, &'a Bound<'py, PyAny>),
}

/// The header's description and, when it declares any schema metadata, its entry.
pub(crate) struct AttachedHeader<'py> {
    pub(crate) description: Option<String>,
    pub(crate) schema: Option<HeaderSchema<'py>>,
}

/// A header schema entry's Python contract objects, enum columns and retained fact.
pub(crate) struct HeaderSchema<'py> {
    pub(crate) columns: Bound<'py, PyTuple>,
    pub(crate) audits: Bound<'py, PyTuple>,
    pub(crate) dynamic_columns: Bound<'py, PyTuple>,
    pub(crate) type_enforcement: bool,
    pub(crate) enum_columns: Bound<'py, PyDict>,
    pub(crate) generated_usages: Vec<Bound<'py, PyAny>>,
    pub(crate) fact: ModelSchemaFact,
}

/// The attached header entry, raising the attachment's errors in its order.
pub(crate) fn header_schema<'py>(
    py: Python<'py>,
    context: &LoopContext<'_, 'py>,
    source: &HeaderSource<'_, 'py>,
) -> PyResult<AttachedHeader<'py>> {
    let description: Option<String> = description(context, source)?;
    let columns: Option<Bound<'py, PyAny>> = present(source.values, COLUMNS_KEY)?;
    let audits: Option<Bound<'py, PyAny>> = present(source.values, AUDITS_KEY)?;
    let dynamic: Option<Bound<'py, PyAny>> = present(source.values, DYNAMIC_COLUMNS_KEY)?;
    let factories: Option<Bound<'py, PyAny>> = present(source.values, AUDIT_FACTORIES_KEY)?;
    if description.is_none()
        && columns.is_none()
        && audits.is_none()
        && dynamic.is_none()
        && factories.is_none()
    {
        return Ok(AttachedHeader {
            description,
            schema: None,
        });
    }
    let none: Bound<'py, PyAny> = py.None().into_bound(py);
    let node = |value: Option<Bound<'py, PyAny>>| PyNode(value.unwrap_or_else(|| none.clone()));
    let model: (&str, &str) = (source.name, source.relative_path);
    let metadata = parse_header_metadata(&node(columns), &node(audits), source.relative_path);
    let parsed_columns = metadata
        .columns
        .map_err(|error| raised_config_error(py, context, error))?;
    let families = dynamic_families(py, context, &node(dynamic), model)?;
    let parsed_audits = metadata
        .audits
        .map_err(|error| raised_config_error(py, context, error))?;
    let available: Vec<String> = context.classes.audit_factories.keys().extract()?;
    let references: Vec<String> = audit_factory_references(&node(factories), model, &available)
        .map_err(|error| raised_config_error(py, context, error))?;
    let direct_audits: Bound<'py, PyTuple> = audit_tuple(py, context.contracts, &parsed_audits)?;
    let (generated, generated_identities) = factory_audits(py, context, &references)?;
    let direct_identities: Vec<String> = direct_audits
        .iter()
        .map(|audit| audit_identity(&audit))
        .collect::<PyResult<_>>()?;
    merged_audit_identities(&direct_identities, &generated_identities, model)
        .map_err(|error| raised_config_error(py, context, error))?;
    let migrations: Vec<ColumnMigration> = parsed_columns
        .iter()
        .map(column_migration)
        .collect::<PyResult<_>>()?;
    if let Some(error) = column_migration_error(source.name, source.values, &migrations)? {
        let error = native_config_error(py, error)?.into_bound(py).into_any();
        return Err(config_error(context.classes, &error, Some(source.values)));
    }
    let type_enforcement: bool = !families.is_empty()
        || parsed_columns.iter().any(|column| {
            column
                .column_type
                .as_ref()
                .is_some_and(|node| !node.0.is_none())
        });
    let columns: Bound<'py, PyTuple> =
        column_tuple(py, context.contracts, &parsed_columns, source.locations)?;
    let audits: Bound<'py, PyTuple> = PyTuple::new(
        py,
        direct_audits.iter().chain(generated).collect::<Vec<_>>(),
    )?;
    let families: Vec<Bound<'py, PyAny>> = dynamic_family_objects(py, context, &families)?;
    let resolved: EnumColumns<'py> =
        enum_columns(context, source.visible, source.values, &columns)?;
    let fact: ModelSchemaFact =
        schema_fact(schema_row(&resolved.columns, audits.len(), &families)?);
    Ok(AttachedHeader {
        description,
        schema: Some(HeaderSchema {
            columns: resolved.columns,
            audits,
            dynamic_columns: PyTuple::new(py, families)?,
            type_enforcement,
            enum_columns: resolved.declarations,
            generated_usages: resolved.usages,
            fact,
        }),
    })
}

/// The header's dynamic column families, compiling each `name_pattern` with Python's `re`.
fn dynamic_families(
    py: Python<'_>,
    context: &LoopContext<'_, '_>,
    raw: &PyNode<'_>,
    model: (&str, &str),
) -> PyResult<Vec<DynamicFamily>> {
    let compile: Bound<'_, PyAny> = py.import(RE_MODULE)?.getattr(COMPILE_FUNCTION)?;
    let pattern_error_class: Bound<'_, PyAny> = py.import(RE_MODULE)?.getattr(ERROR_CLASS)?;
    let failure: RefCell<Option<PyErr>> = RefCell::new(None);
    let pattern_error = |pattern: &str| match compile.call1((pattern,)) {
        Ok(_) => None,
        Err(error) if error.is_instance(py, &pattern_error_class) => {
            Some(error.value(py).to_string())
        }
        Err(error) => {
            failure.replace(Some(error));
            Some(String::new())
        }
    };
    let parsed = parse_dynamic_columns(raw, model, &pattern_error);
    if let Some(error) = failure.into_inner() {
        return Err(error);
    }
    parsed.map_err(|error| raised_config_error(py, context, error))
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
