//! Native facts of declared schema columns and families, read once from their Python specs.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use sqlbuild_analysis::compiled_project::models::{
    DynamicFamilyFact, ModelSchemaFact, SchemaColumnFact,
};
use sqlbuild_core::text::main::python_casefold::python_casefold;
use sqlbuild_model_config::header_metadata::models::DynamicFamily;

const NAME_FIELD: &str = "name";
const TYPE_FIELD: &str = "type";
const NULLABLE_FIELD: &str = "nullable";
const DESCRIPTION_FIELD: &str = "description";
const MIGRATE_FROM_FIELD: &str = "migrate_from";
const AUDITS_FIELD: &str = "audits";
const LOCATION_FIELD: &str = "location";
const PATH_FIELD: &str = "path";
const DEFINITION_NAME_FIELD: &str = "definition_name";
const COLUMNS_FIELD: &str = "columns";
const DYNAMIC_COLUMNS_FIELD: &str = "dynamic_columns";
const TYPE_ENFORCEMENT_FIELD: &str = "type_enforcement";
const MODEL_SCHEMA_FIELD: &str = "model_schema";
const PIVOT_COLUMN_FIELD: &str = "pivot_column";
const VALUE_COLUMN_FIELD: &str = "value_column";
const AGGREGATE_FIELD: &str = "aggregate";
const NAME_PATTERN_FIELD: &str = "name_pattern";

/// A Python column spec's fact; `declared_outside_model` compares its location with `model_path`.
pub(crate) fn python_column_fact(
    column: &Bound<'_, PyAny>,
    model_path: Option<&Bound<'_, PyAny>>,
) -> PyResult<SchemaColumnFact> {
    let mut audit_definitions: Vec<String> = Vec::new();
    if let Some(audits) = present(column, AUDITS_FIELD)? {
        for audit in audits.try_iter()? {
            audit_definitions.push(audit?.getattr(DEFINITION_NAME_FIELD)?.extract()?);
        }
    }
    let (location_path, declared_outside_model) = match present(column, LOCATION_FIELD)? {
        Some(location) => {
            let path: Bound<'_, PyAny> = location.getattr(PATH_FIELD)?;
            let outside: bool = match model_path {
                Some(model_path) => !path.is(model_path) && path.ne(model_path)?,
                None => true,
            };
            (Some(path.str()?.to_string()), outside)
        }
        None => (None, false),
    };
    Ok(SchemaColumnFact {
        name: column.getattr(NAME_FIELD)?.str()?.extract()?,
        data_type: optional(column, TYPE_FIELD)?,
        nullable: optional(column, NULLABLE_FIELD)?,
        description: optional(column, DESCRIPTION_FIELD)?,
        migrate_from: optional(column, MIGRATE_FROM_FIELD)?,
        audit_definitions,
        location_path,
        declared_outside_model,
    })
}

/// The facts of every column spec in `columns`.
pub(crate) fn python_column_facts(
    columns: &Bound<'_, PyAny>,
    model_path: Option<&Bound<'_, PyAny>>,
) -> PyResult<Vec<SchemaColumnFact>> {
    columns
        .try_iter()?
        .map(|column| python_column_fact(&column?, model_path))
        .collect()
}

/// The fact of a hand-built model's `SchemaModelEntry`, or `None` without one.
pub(crate) fn entry_schema_fact(
    entry: &Bound<'_, PyAny>,
    model_path: &Bound<'_, PyAny>,
) -> PyResult<Option<ModelSchemaFact>> {
    if entry.is_none() {
        return Ok(None);
    }
    let mut dynamic_columns: Vec<DynamicFamilyFact> = Vec::new();
    for family in entry.getattr(DYNAMIC_COLUMNS_FIELD)?.try_iter()? {
        let family: Bound<'_, PyAny> = family?;
        dynamic_columns.push(family_fact(&DynamicFamily {
            name: family.getattr(NAME_FIELD)?.extract()?,
            pivot_column: family.getattr(PIVOT_COLUMN_FIELD)?.extract()?,
            value_column: family.getattr(VALUE_COLUMN_FIELD)?.extract()?,
            aggregate: family.getattr(AGGREGATE_FIELD)?.extract()?,
            data_type: family.getattr(TYPE_FIELD)?.extract()?,
            name_pattern: family.getattr(NAME_PATTERN_FIELD)?.extract()?,
        }));
    }
    Ok(Some(ModelSchemaFact {
        audit_count: u32::try_from(entry.getattr(AUDITS_FIELD)?.len()?).unwrap_or(u32::MAX),
        columns: python_column_facts(&entry.getattr(COLUMNS_FIELD)?, Some(model_path))?,
        dynamic_columns,
        type_enforcement: entry.getattr(TYPE_ENFORCEMENT_FIELD)?.is_truthy()?,
        named_schema: !entry.getattr(MODEL_SCHEMA_FIELD)?.is_none(),
    }))
}

/// A parsed dynamic column family's fact, keyed by its casefolded name.
pub(crate) fn family_fact(family: &DynamicFamily) -> DynamicFamilyFact {
    DynamicFamilyFact {
        key: python_casefold(&family.name),
        name: family.name.clone(),
        pivot_column: family.pivot_column.clone(),
        value_column: family.value_column.clone(),
        aggregate: family.aggregate.clone(),
        data_type: family.data_type.clone(),
        name_pattern: family.name_pattern.clone(),
    }
}

/// An attribute's value, `None` when it is missing or `None`.
fn present<'py>(spec: &Bound<'py, PyAny>, name: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
    Ok(spec.getattr_opt(name)?.filter(|value| !value.is_none()))
}

fn optional<'py, T: pyo3::FromPyObject<'py>>(
    spec: &Bound<'py, PyAny>,
    name: &str,
) -> PyResult<Option<T>> {
    present(spec, name)?
        .map(|value| value.extract())
        .transpose()
}
