//! A model's `model_schema`: resolved, checked for visibility, and merged into its header columns.

use std::path::Path;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple, PyTupleMethods};
use sqlbuild_scopes::scope_index::main::path_visible::path_visible;
use sqlbuild_scopes::scope_index::models::{
    DeclaredScope, ResourceIdentity, ResourceKind, ScopeKind,
};

use crate::bindings::_helpers::compiled_project::model_loop::{LoopContext, compile_error};
use crate::bindings::_helpers::compiled_project::model_loop_inputs::present;

const MODEL_SCHEMA_KEY: &str = "model_schema";
const NAME_FIELD: &str = "name";
const TYPE_FIELD: &str = "type";
const NULLABLE_FIELD: &str = "nullable";
const DESCRIPTION_FIELD: &str = "description";
const AUDITS_FIELD: &str = "audits";
const MIGRATE_FROM_FIELD: &str = "migrate_from";
const LOCATION_FIELD: &str = "location";
const PATH_FIELD: &str = "path";
const LINE_FIELD: &str = "line";
const COLUMNS_FIELD: &str = "columns";
const SCOPE_FIELD: &str = "scope";
const VALUE_FIELD: &str = "value";
const IDENTITY_FIELD: &str = "identity";
const OWNER_FIELD: &str = "owner";
const KIND_FIELD: &str = "kind";
const OWNING_PATH_FIELD: &str = "owning_path";
const OWNERSHIP_ROOT_FIELD: &str = "ownership_root";
const CONSUMER_FIELD: &str = "consumer";
const DECLARATION_FIELD: &str = "declaration";
const LOWER_METHOD: &str = "lower";
const STRIP_METHOD: &str = "strip";
const CURRENT_FOLDER: &str = ".";
const SCHEMA_ROLE: &str = "schemas";
const INACCESSIBLE_CODE: &str = "S006";
const SCHEMA_KIND: &str = "schema";
/// `SchemaColumn` fields a named-schema column keeps when a header column augments it.
const KEPT_NAMED_FIELDS: [&str; 6] = [
    "name",
    "type",
    "nullable",
    "description",
    "meta",
    "location",
];

/// The reusable schema a model names: its columns, name, description and enum column types.
pub(crate) struct ModelSchema<'py> {
    pub(crate) declaration: Bound<'py, PyAny>,
    pub(crate) name: String,
}

/// `_resolve_model_schema`: `None`, or the public schema the model's config names.
pub(crate) fn model_schema<'py>(
    context: &LoopContext<'_, 'py>,
    values: &Bound<'py, PyDict>,
    model_name: &str,
) -> PyResult<Option<ModelSchema<'py>>> {
    let Some(raw) = present(values, MODEL_SCHEMA_KEY)? else {
        return Ok(None);
    };
    let Ok(name) = raw.downcast::<PyString>() else {
        return Err(invalid_name(context, model_name));
    };
    if !name.call_method0(STRIP_METHOD)?.is_truthy()? {
        return Err(invalid_name(context, model_name));
    }
    let schemas: &Bound<'py, PyDict> = &context.classes.model_schemas;
    let Some(declaration) = schemas.get_item(name)? else {
        let mut available: Vec<String> = schemas.keys().extract()?;
        available.sort_unstable();
        let listed: String = if available.is_empty() {
            "none".to_owned()
        } else {
            available.join(", ")
        };
        let message: String = format!(
            "model '{model_name}' references unknown model_schema '{name}'; available schemas: \
             {listed}"
        );
        return Err(compile_error(context.classes, &message, None));
    };
    Ok(Some(ModelSchema {
        declaration,
        name: name.extract()?,
    }))
}

/// `named_declaration_usages`: the schema usage, reporting S006; `None` defers to Python.
pub(crate) fn schema_usages<'py>(
    context: &LoopContext<'_, 'py>,
    schema: &ModelSchema<'py>,
    consumer: &Bound<'py, PyAny>,
    model: (&str, &str),
) -> PyResult<Option<Vec<Bound<'py, PyAny>>>> {
    let (model_name, relative_path) = model;
    let Some(record) = context.classes.schema_records.get_item(&schema.name)? else {
        return Ok(Some(Vec::new()));
    };
    let label: String = relative_path.replace(std::path::MAIN_SEPARATOR, "/");
    let Ok(visible) = path_visible(&declared_scope(&record)?, &label) else {
        return Ok(None);
    };
    if !visible {
        report_inaccessible(context, &record, &schema.name, (model_name, &label))?;
    }
    let fields: Bound<'py, PyDict> = PyDict::new(consumer.py());
    fields.set_item(CONSUMER_FIELD, consumer)?;
    fields.set_item(DECLARATION_FIELD, record.getattr(IDENTITY_FIELD)?)?;
    Ok(Some(vec![
        context.classes.usage_record.call((), Some(&fields))?,
    ]))
}

/// The schema's column names, which validation reads as the declared columns.
pub(crate) fn schema_column_names(schema: &ModelSchema<'_>) -> PyResult<Vec<String>> {
    schema
        .declaration
        .getattr(COLUMNS_FIELD)?
        .try_iter()?
        .map(|column| column?.getattr(NAME_FIELD)?.extract())
        .collect()
}

/// `model_schema_enum_declarations`: the schema's column types that name a project enum.
pub(crate) fn schema_enums<'py>(
    context: &LoopContext<'_, 'py>,
    schema: &ModelSchema<'py>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = schema.declaration.py();
    let enums: Bound<'py, PyDict> = PyDict::new(py);
    for column in schema.declaration.getattr(COLUMNS_FIELD)?.try_iter()? {
        let column_type: Bound<'py, PyAny> = column?.getattr(TYPE_FIELD)?;
        if column_type.is_none() {
            continue;
        }
        if let Some(declaration) = context.classes.schema_enums.get_item(&column_type)? {
            enums.set_item(column_type, declaration)?;
        }
    }
    Ok(enums)
}

/// `_merge_model_schema_columns`: named columns first, augmented by header audits, then the rest.
pub(crate) fn merged_columns<'py>(
    context: &LoopContext<'_, 'py>,
    schema: &ModelSchema<'py>,
    local: &Bound<'py, PyTuple>,
    model: (&str, &str),
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = local.py();
    let mut merged: Vec<Bound<'py, PyAny>> = schema
        .declaration
        .getattr(COLUMNS_FIELD)?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let mut keys: Vec<Bound<'py, PyAny>> = Vec::with_capacity(merged.len());
    for column in &merged {
        keys.push(column.getattr(NAME_FIELD)?.call_method0(LOWER_METHOD)?);
    }
    let mut additional: Vec<Bound<'py, PyAny>> = Vec::new();
    for column in local.iter() {
        let key: Bound<'py, PyAny> = column.getattr(NAME_FIELD)?.call_method0(LOWER_METHOD)?;
        let mut named_index: Option<usize> = None;
        for (index, candidate) in keys.iter().enumerate() {
            if candidate.eq(&key)? {
                named_index = Some(index);
            }
        }
        let Some(index) = named_index else {
            additional.push(column);
            continue;
        };
        check_augmentation(context, &column, &merged[index], model)?;
        merged[index] = augmented(context, &merged[index], &column)?;
    }
    merged.extend(additional);
    PyTuple::new(py, merged)
}

fn augmented<'py>(
    context: &LoopContext<'_, 'py>,
    named: &Bound<'py, PyAny>,
    local: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = named.py();
    let mut audits: Vec<Bound<'py, PyAny>> = named
        .getattr(AUDITS_FIELD)?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    for audit in local.getattr(AUDITS_FIELD)?.try_iter()? {
        let audit: Bound<'py, PyAny> = audit?;
        let mut present: bool = false;
        for existing in &audits {
            if existing.eq(&audit)? {
                present = true;
                break;
            }
        }
        if !present {
            audits.push(audit);
        }
    }
    let fields: Bound<'py, PyDict> = PyDict::new(py);
    for field in KEPT_NAMED_FIELDS {
        fields.set_item(field, named.getattr(field)?)?;
    }
    fields.set_item(AUDITS_FIELD, PyTuple::new(py, audits)?)?;
    fields.set_item(MIGRATE_FROM_FIELD, local.getattr(MIGRATE_FROM_FIELD)?)?;
    context.contracts.schema_column.call((), Some(&fields))
}

/// `_validate_model_schema_audit_augmentation`.
fn check_augmentation(
    context: &LoopContext<'_, '_>,
    local: &Bound<'_, PyAny>,
    named: &Bound<'_, PyAny>,
    model: (&str, &str),
) -> PyResult<()> {
    let (model_name, relative_path) = model;
    let name: String = local.getattr(NAME_FIELD)?.str()?.to_string();
    let location: Bound<'_, PyAny> = named.getattr(LOCATION_FIELD)?;
    let origin: String = if location.is_none() {
        "the named schema".to_owned()
    } else {
        format!(
            "{}:{}",
            location.getattr(PATH_FIELD)?.str()?,
            location.getattr(LINE_FIELD)?.str()?
        )
    };
    let mut overridden: Vec<&str> = Vec::new();
    for field in [TYPE_FIELD, NULLABLE_FIELD, DESCRIPTION_FIELD] {
        if !local.getattr(field)?.is_none() {
            overridden.push(field);
        }
    }
    if !overridden.is_empty() {
        let message: String = format!(
            "model '{model_name}' in {relative_path} cannot override {} for named-schema column \
             '{name}' from {origin}; only audit augmentation is supported",
            overridden.join(", ")
        );
        return Err(compile_error(context.classes, &message, None));
    }
    if !local.getattr(AUDITS_FIELD)?.is_truthy()? && local.getattr(MIGRATE_FROM_FIELD)?.is_none() {
        let message: String = format!(
            "model '{model_name}' in {relative_path} redeclares named-schema column '{name}' from \
             {origin} without audits or migrate_from; only audit augmentation and column \
             migrations are supported"
        );
        return Err(compile_error(context.classes, &message, None));
    }
    Ok(())
}

fn invalid_name(context: &LoopContext<'_, '_>, model_name: &str) -> pyo3::PyErr {
    let message: String = format!("model '{model_name}': model_schema must be a non-empty string");
    compile_error(context.classes, &message, None)
}

/// The scope facts of a Python `DeclarationRecord`.
fn declared_scope(record: &Bound<'_, PyAny>) -> PyResult<DeclaredScope> {
    let scope: String = record
        .getattr(SCOPE_FIELD)?
        .getattr(VALUE_FIELD)?
        .extract()?;
    let owner: Bound<'_, PyAny> = record.getattr(IDENTITY_FIELD)?.getattr(OWNER_FIELD)?;
    let owner: Option<ResourceIdentity> = if owner.is_none() {
        None
    } else {
        let kind: String = owner.getattr(KIND_FIELD)?.getattr(VALUE_FIELD)?.extract()?;
        let name: String = owner.getattr(NAME_FIELD)?.extract()?;
        ResourceKind::parse(&kind).map(|kind| ResourceIdentity { kind, name })
    };
    Ok(DeclaredScope {
        scope: ScopeKind::parse(&scope).unwrap_or(ScopeKind::Global),
        owner,
        owning_path: record.getattr(OWNING_PATH_FIELD)?.extract()?,
    })
}

/// Report Python's S006 diagnostic for a schema the model's folder cannot see.
fn report_inaccessible(
    context: &LoopContext<'_, '_>,
    record: &Bound<'_, PyAny>,
    name: &str,
    model: (&str, &str),
) -> PyResult<()> {
    let py: Python<'_> = record.py();
    let (model_name, label) = model;
    let folder: &str = Path::new(label)
        .parent()
        .and_then(Path::to_str)
        .filter(|parent| !parent.is_empty())
        .unwrap_or(CURRENT_FOLDER);
    let owning_path: Bound<'_, PyAny> = record.getattr(OWNING_PATH_FIELD)?;
    let owner: String = if owning_path.is_truthy()? {
        owning_path.str()?.to_string()
    } else {
        record
            .getattr(OWNERSHIP_ROOT_FIELD)?
            .getattr(PATH_FIELD)?
            .str()?
            .to_string()
    };
    let record_path: String = record.getattr(PATH_FIELD)?.str()?.to_string();
    let scope: String = record
        .getattr(SCOPE_FIELD)?
        .getattr(VALUE_FIELD)?
        .extract()?;
    let fields: Bound<'_, PyDict> = PyDict::new(py);
    fields.set_item("phase", "compile")?;
    fields.set_item("severity", "error")?;
    fields.set_item("code", INACCESSIBLE_CODE)?;
    fields.set_item(
        "message",
        format!(
            "Schema '{name}' is not visible from '{label}'. It is defined at {record_path} with \
             {scope} scope owned by '{owner}'"
        ),
    )?;
    fields.set_item("resource_type", "model")?;
    fields.set_item("resource_name", model_name)?;
    fields.set_item("path", context.classes.path_class.call1((label,))?)?;
    fields.set_item(
        "help",
        format!(
            "move '{record_path}' to a {SCHEMA_ROLE}/ role owned by '{folder}' or one of its \
             parent folders, or to the project-wide {SCHEMA_ROLE}/ when consumers span resource \
             trees"
        ),
    )?;
    let diagnostic: Bound<'_, PyAny> = context
        .classes
        .compiler_diagnostic
        .call((), Some(&fields))?;
    let key: Bound<'_, PyTuple> = PyTuple::new(py, [INACCESSIBLE_CODE, label, SCHEMA_KIND, name])?;
    let arguments: Bound<'_, PyDict> = PyDict::new(py);
    arguments.set_item("key", key)?;
    arguments.set_item("diagnostic", diagnostic)?;
    context
        .classes
        .report_diagnostic
        .call((), Some(&arguments))?;
    Ok(())
}
