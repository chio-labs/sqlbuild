//! A model's `model_schema`: resolved, checked for visibility, and merged into its header columns.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyTuple, PyTupleMethods};

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
const LOWER_METHOD: &str = "lower";
const STRIP_METHOD: &str = "strip";
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
