//! A model's MODEL header attached as its schema entry, by the native header parser.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods, PyTuple, PyTupleMethods};
use sqlbuild_analysis::compiled_project::models::{
    DynamicFamilyFact, ModelSchemaFact, SchemaColumnFact,
};
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
    EnumColumns, audit_identity, dynamic_family_objects, enum_columns, factory_audits,
};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::present;
use crate::bindings::_helpers::compiled_project::model_loop_schema::{
    DeclaredColumns, ModelSchema, merged_columns, schema_enums,
};
use crate::bindings::_helpers::compiled_project::schema_facts::family_fact;
use crate::bindings::_helpers::discovery::model_file_record::NativeModelFile;
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
const ENUMS_FIELD: &str = "enums";

/// What a model's header schema entry is attached from.
pub(crate) struct HeaderSource<'a, 'py> {
    pub(crate) name: &'a str,
    pub(crate) values: &'a Bound<'py, PyDict>,
    pub(crate) model_file: &'a NativeModelFile,
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
        .map_err(|error| raised_config_error(py, error))?;
    let locations: Bound<'py, PyDict> = source.model_file.header_locations(py)?;
    let model_path: &Bound<'py, PyAny> = source.model_file.paths(py).1;
    let local_columns: DeclaredColumns<'py> = DeclaredColumns {
        specs: column_tuple(py, context.contracts, &parsed_columns, &locations)?
            .iter()
            .collect(),
        facts: local_column_facts(&parsed_columns)?,
    };
    let columns: DeclaredColumns<'py> = match source.schema {
        Some(schema) => merged_columns(
            context,
            schema,
            local_columns,
            (source.name, source.relative_path, model_path),
        )?,
        None => local_columns,
    };
    let families = dynamic_families(py, &node(dynamic), model)?;
    let parsed_audits = metadata
        .audits
        .map_err(|error| raised_config_error(py, error))?;
    let available: Vec<String> = context.classes.audit_factories.keys().extract()?;
    let references: Vec<String> = audit_factory_references(&node(factories), model, &available)
        .map_err(|error| raised_config_error(py, error))?;
    let direct_audits: Bound<'py, PyTuple> = audit_tuple(py, context.contracts, &parsed_audits)?;
    let (generated, generated_identities) = factory_audits(py, context, &references)?;
    let direct_identities: Vec<String> = direct_audits
        .iter()
        .map(|audit| audit_identity(&audit))
        .collect::<PyResult<_>>()?;
    merged_audit_identities(&direct_identities, &generated_identities, model)
        .map_err(|error| raised_config_error(py, error))?;
    let migrations: Vec<ColumnMigration> = columns
        .facts
        .iter()
        .map(|column| ColumnMigration {
            name: column.name.clone(),
            migrate_from: column.migrate_from.clone(),
        })
        .collect();
    if let Some(error) = column_migration_error(source.name, source.values, &migrations)? {
        let error = native_config_error(py, error)?.into_bound(py).into_any();
        return Err(config_error(&error, Some(source.values)));
    }
    let type_enforcement: bool = !families.is_empty()
        || columns
            .facts
            .iter()
            .any(|column| column.data_type.is_some());
    let family_facts: Vec<DynamicFamilyFact> = families.iter().map(family_fact).collect();
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
        enum_columns(context, (&enums, source.visible), source.values, columns)?;
    let fact: ModelSchemaFact = ModelSchemaFact {
        audit_count: u32::try_from(audits.len()).unwrap_or(u32::MAX),
        columns: resolved.facts,
        dynamic_columns: family_facts,
        type_enforcement,
        named_schema: source.schema.is_some(),
    };
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
    raw: &PyNode<'_>,
    model: (&str, &str),
) -> PyResult<Vec<DynamicFamily>> {
    parse_dynamic_columns(raw, model).map_err(|error| raised_config_error(py, error))
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
    error: sqlbuild_model_config::errors::ConfigError,
) -> pyo3::PyErr {
    match native_config_error(py, error) {
        Ok(native) => config_error(native.bind(py).as_any(), None),
        Err(failure) => failure,
    }
}

/// The facts of the header's own columns, which are declared in the model file.
fn local_column_facts(parsed: &[ParsedColumn<PyNode<'_>>]) -> PyResult<Vec<SchemaColumnFact>> {
    let mut facts: Vec<SchemaColumnFact> = Vec::with_capacity(parsed.len());
    for column in parsed {
        let text = |node: Option<&PyNode<'_>>| -> PyResult<Option<String>> {
            node.map(|node| node.0.extract()).transpose()
        };
        facts.push(SchemaColumnFact {
            name: column.name.0.str()?.extract()?,
            data_type: text(column.column_type.as_ref())?,
            nullable: column
                .nullable
                .as_ref()
                .map(|node| node.0.extract())
                .transpose()?,
            described: column.description.is_some(),
            migrate_from: text(column.migrate_from.as_ref())?,
            audit_definitions: column
                .audits
                .iter()
                .map(|audit| audit.definition_name.0.extract())
                .collect::<PyResult<_>>()?,
            location_path: None,
        });
    }
    Ok(facts)
}
