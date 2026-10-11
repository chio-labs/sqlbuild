//! A model's MODEL header attached as its schema entry, by the native header parser.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods, PyTuple, PyTupleMethods};
use sqlbuild_analysis::compiled_project::models::ModelSchemaFact;
use sqlbuild_model_config::header_metadata::main::audit_factory_references::audit_factory_references;
use sqlbuild_model_config::header_metadata::main::merged_audit_identities::merged_audit_identities;
use sqlbuild_model_config::header_metadata::main::parse_dynamic_columns::parse_dynamic_columns;
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_model_config::header_metadata::models::DynamicFamily;
use sqlbuild_model_config::model_validation::models::ColumnMigration;

use crate::bindings::_helpers::compiled_project::model_loop::{
    LoopContext, compile_error, config_error,
};
use crate::bindings::_helpers::compiled_project::model_loop_contracts::{
    EnumColumns, audit_identity, dynamic_family_objects, enum_columns, factory_audits, schema_row,
};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::present;
use crate::bindings::_helpers::compiled_project::model_loop_schema::{
    ModelSchema, merged_columns, schema_enums,
};
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
const STRIP_METHOD: &str = "strip";
const NAME_FIELD: &str = "name";
const TYPE_FIELD: &str = "type";
const MIGRATE_FROM_FIELD: &str = "migrate_from";
const ENUMS_FIELD: &str = "enums";

/// What a model's header schema entry is attached from.
pub(crate) struct HeaderSource<'a, 'py> {
    pub(crate) name: &'a str,
    pub(crate) values: &'a Bound<'py, PyDict>,
    pub(crate) locations: &'a Bound<'py, PyDict>,
    pub(crate) relative_path: &'a str,
    /// The model's visible declarations and the identity its usages are recorded for.
    pub(crate) visible: (&'a Bound<'py, PyAny>, &'a Bound<'py, PyAny>),
    pub(crate) schema: Option<&'a ModelSchema<'py>>,
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
    pub(crate) model_schema: Option<String>,
    pub(crate) fact: ModelSchemaFact,
}

/// The attached header entry, raising the attachment's errors in its order.
pub(crate) fn header_schema<'py>(
    py: Python<'py>,
    context: &LoopContext<'_, 'py>,
    source: &HeaderSource<'_, 'py>,
) -> PyResult<AttachedHeader<'py>> {
    let description: Option<String> = match (description(context, source)?, source.schema) {
        (None, Some(schema)) => schema.declaration.getattr(DESCRIPTION_KEY)?.extract()?,
        (description, _) => description,
    };
    let columns: Option<Bound<'py, PyAny>> = present(source.values, COLUMNS_KEY)?;
    let audits: Option<Bound<'py, PyAny>> = present(source.values, AUDITS_KEY)?;
    let dynamic: Option<Bound<'py, PyAny>> = present(source.values, DYNAMIC_COLUMNS_KEY)?;
    let factories: Option<Bound<'py, PyAny>> = present(source.values, AUDIT_FACTORIES_KEY)?;
    if source.schema.is_none()
        && description.is_none()
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
    let local_columns: Bound<'py, PyTuple> =
        column_tuple(py, context.contracts, &parsed_columns, source.locations)?;
    let columns: Bound<'py, PyTuple> = match source.schema {
        Some(schema) => merged_columns(context, schema, &local_columns, model)?,
        None => local_columns,
    };
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
    let migrations: Vec<ColumnMigration> = columns
        .iter()
        .map(|column| column_migration(&column))
        .collect::<PyResult<_>>()?;
    if let Some(error) = column_migration_error(source.name, source.values, &migrations)? {
        let error = native_config_error(py, error)?.into_bound(py).into_any();
        return Err(config_error(context.classes, &error, Some(source.values)));
    }
    let mut type_enforcement: bool = !families.is_empty();
    for column in columns.iter() {
        type_enforcement |= !column.getattr(TYPE_FIELD)?.is_none();
    }
    let audits: Bound<'py, PyTuple> = PyTuple::new(
        py,
        direct_audits.iter().chain(generated).collect::<Vec<_>>(),
    )?;
    let families: Vec<Bound<'py, PyAny>> = dynamic_family_objects(py, context, &families)?;
    let enums: Bound<'py, PyDict> = source.visible.0.getattr(ENUMS_FIELD)?.downcast_into()?;
    let enums: Bound<'py, PyDict> = match source.schema {
        Some(schema) => {
            let merged: Bound<'py, PyDict> = enums.copy()?;
            merged.update(schema_enums(context, schema)?.as_mapping())?;
            merged
        }
        None => enums,
    };
    let resolved: EnumColumns<'py> =
        enum_columns(context, (&enums, source.visible), source.values, &columns)?;
    let fact: ModelSchemaFact = schema_fact(schema_row(
        &resolved.columns,
        (
            audits.len(),
            &context.classes.path_class.call1((source.relative_path,))?,
        ),
        &families,
        (type_enforcement, source.schema.is_some()),
    )?);
    Ok(AttachedHeader {
        description,
        schema: Some(HeaderSchema {
            columns: resolved.columns,
            audits,
            dynamic_columns: PyTuple::new(py, families)?,
            type_enforcement,
            enum_columns: resolved.declarations,
            generated_usages: resolved.usages,
            model_schema: source.schema.map(|schema| schema.name.clone()),
            fact,
        }),
    })
}

/// The header's dynamic column families, each `name_pattern` compiled natively.
fn dynamic_families(
    py: Python<'_>,
    context: &LoopContext<'_, '_>,
    raw: &PyNode<'_>,
    model: (&str, &str),
) -> PyResult<Vec<DynamicFamily>> {
    parse_dynamic_columns(raw, model).map_err(|error| raised_config_error(py, context, error))
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

fn column_migration(column: &Bound<'_, PyAny>) -> PyResult<ColumnMigration> {
    Ok(ColumnMigration {
        name: column.getattr(NAME_FIELD)?.str()?.to_string(),
        migrate_from: column.getattr(MIGRATE_FROM_FIELD)?.extract()?,
    })
}
