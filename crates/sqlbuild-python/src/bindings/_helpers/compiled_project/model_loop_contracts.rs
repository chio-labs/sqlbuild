//! Header contract objects the model loop builds: factory audits, dynamic families, enum columns.

use pyo3::BoundObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple, PyTupleMethods};
use sqlbuild_model_config::header_metadata::models::DynamicFamily;

use crate::bindings::_helpers::compiled_project::model_loop::LoopContext;
use crate::bindings::_helpers::compiled_project::project::{
    DynamicFamilyPy, SchemaColumnPy, SchemaPy,
};

const CASES_ATTRIBUTE: &str = "cases";
const RELATIVE_PATH_ATTRIBUTE: &str = "relative_path";
const LINE_ATTRIBUTE: &str = "line";
const DEFINITION_ATTRIBUTE: &str = "definition";
const DEFINITION_NAME_FIELD: &str = "definition_name";
const ARGUMENTS_FIELD: &str = "arguments";
const NAME_FIELD: &str = "name";
const TYPE_FIELD: &str = "type";
const NULLABLE_FIELD: &str = "nullable";
const AUDITS_FIELD: &str = "audits";
const MEMBERS_FIELD: &str = "members";
const VALUE_FIELD: &str = "value";
const VALUES_ARGUMENT: &str = "values";
const SCALAR_TYPE_ATTRIBUTE: &str = "scalar_type";
const ENUM_VISIBILITY_ATTRIBUTE: &str = "enum_visibility";
const DECLARATION_FIELD: &str = "declaration";
const THROUGH_FIELD: &str = "through";
const CONSUMER_FIELD: &str = "consumer";
const KIND_FIELD: &str = "kind";
const PATH_FIELD: &str = "path";
const COLUMN_FIELD: &str = "column";
const LOCATION_FIELD: &str = "location";
const CASEFOLD_METHOD: &str = "casefold";
const ACCEPTED_VALUES_AUDIT: &str = "accepted_values";
const CONTRACT_KEY: &str = "contract";
/// `AuditCase` fields copied onto each generated `SchemaAuditInstance` under the same name.
const COPIED_CASE_FIELDS: [&str; 8] = [
    "name",
    "severity",
    "run_scope",
    "always_run",
    "description",
    "thresholds",
    "minimum_samples",
    "evidence_limit",
];
/// `SchemaColumn` fields `dataclasses.replace` carries over unchanged.
const KEPT_COLUMN_FIELDS: [&str; 6] = [
    "name",
    "nullable",
    "description",
    "meta",
    "location",
    "migrate_from",
];
const PIVOT_COLUMN_FIELD: &str = "pivot_column";
const VALUE_COLUMN_FIELD: &str = "value_column";
const AGGREGATE_FIELD: &str = "aggregate";
const NAME_PATTERN_FIELD: &str = "name_pattern";

/// A model's enum-typed columns resolved to scalar types, and the usages they generate.
pub(crate) struct EnumColumns<'py> {
    pub(crate) columns: Bound<'py, PyTuple>,
    /// Column name to its enum declaration, as `CompileModelInput.enum_columns` holds them.
    pub(crate) declarations: Bound<'py, PyDict>,
    pub(crate) usages: Vec<Bound<'py, PyAny>>,
}

/// Each referenced factory's cases as audit instances, with their identities.
pub(crate) fn factory_audits<'py>(
    py: Python<'py>,
    context: &LoopContext<'_, 'py>,
    references: &[String],
) -> PyResult<(Vec<Bound<'py, PyAny>>, Vec<String>)> {
    let mut audits: Vec<Bound<'py, PyAny>> = Vec::new();
    let mut identities: Vec<String> = Vec::new();
    for reference in references {
        let Some(factory) = context.classes.audit_factories.get_item(reference)? else {
            continue;
        };
        let location: Bound<'py, PyAny> = keywords(
            &context.contracts.source_location,
            &[
                (PATH_FIELD, factory.getattr(RELATIVE_PATH_ATTRIBUTE)?),
                (LINE_ATTRIBUTE, factory.getattr(LINE_ATTRIBUTE)?),
                (COLUMN_FIELD, 1_u8.into_pyobject_any(py)?),
            ],
        )?;
        for case in factory.getattr(CASES_ATTRIBUTE)?.try_iter()? {
            let case: Bound<'py, PyAny> = case?;
            let fields: Bound<'py, PyDict> = PyDict::new(py);
            fields.set_item(DEFINITION_NAME_FIELD, case.getattr(DEFINITION_ATTRIBUTE)?)?;
            fields.set_item(
                ARGUMENTS_FIELD,
                py.get_type::<PyDict>()
                    .call1((case.getattr(ARGUMENTS_FIELD)?,))?,
            )?;
            for field in COPIED_CASE_FIELDS {
                fields.set_item(field, case.getattr(field)?)?;
            }
            fields.set_item(LOCATION_FIELD, &location)?;
            let audit: Bound<'py, PyAny> = context
                .contracts
                .schema_audit_instance
                .call((), Some(&fields))?;
            identities.push(audit_identity(&audit)?);
            audits.push(audit);
        }
    }
    Ok((audits, identities))
}

/// `audit.name or audit.definition_name`.
pub(crate) fn audit_identity(audit: &Bound<'_, PyAny>) -> PyResult<String> {
    let name: Bound<'_, PyAny> = audit.getattr(NAME_FIELD)?;
    if name.is_truthy()? {
        return name.extract();
    }
    audit.getattr(DEFINITION_NAME_FIELD)?.extract()
}

/// The parsed families as `SchemaDynamicColumnFamily` objects.
pub(crate) fn dynamic_family_objects<'py>(
    py: Python<'py>,
    context: &LoopContext<'_, 'py>,
    families: &[DynamicFamily],
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    families
        .iter()
        .map(|family| {
            keywords(
                &context.contracts.schema_dynamic_column_family,
                &[
                    (NAME_FIELD, family.name.as_str().into_pyobject_any(py)?),
                    (
                        PIVOT_COLUMN_FIELD,
                        family.pivot_column.as_str().into_pyobject_any(py)?,
                    ),
                    (
                        VALUE_COLUMN_FIELD,
                        family.value_column.as_str().into_pyobject_any(py)?,
                    ),
                    (
                        AGGREGATE_FIELD,
                        family.aggregate.as_str().into_pyobject_any(py)?,
                    ),
                    (TYPE_FIELD, family.data_type.as_str().into_pyobject_any(py)?),
                    (
                        NAME_PATTERN_FIELD,
                        family.name_pattern.as_deref().into_pyobject_any(py)?,
                    ),
                ],
            )
        })
        .collect()
}

/// `resolve_enum_contract_columns` and `_generated_enum_usages` for a header schema entry.
pub(crate) fn enum_columns<'py>(
    context: &LoopContext<'_, 'py>,
    visible: (
        &Bound<'py, PyDict>,
        (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    ),
    values: &Bound<'py, PyDict>,
    columns: &Bound<'py, PyTuple>,
) -> PyResult<EnumColumns<'py>> {
    let py: Python<'py> = columns.py();
    let (enums, (declarations, consumer)) = visible;
    let enforced: bool = match values.get_item(CONTRACT_KEY)? {
        Some(value) => value.eq(&context.classes.contract_enforced)?,
        None => false,
    };
    let resolved: Bound<'py, PyDict> = PyDict::new(py);
    let mut resolved_columns: Vec<Bound<'py, PyAny>> = Vec::with_capacity(columns.len());
    for column in columns.iter() {
        let column_type: Bound<'py, PyAny> = column.getattr(TYPE_FIELD)?;
        let key: Bound<'py, PyAny> = if column_type.is_truthy()? {
            column_type
        } else {
            "".into_pyobject_any(py)?
        };
        let Some(declaration) = enums.get_item(&key)? else {
            resolved_columns.push(column);
            continue;
        };
        resolved.set_item(column.getattr(NAME_FIELD)?, &declaration)?;
        let mut audits: Vec<Bound<'py, PyAny>> = column
            .getattr(AUDITS_FIELD)?
            .try_iter()?
            .collect::<PyResult<_>>()?;
        if enforced {
            let generated: Bound<'py, PyAny> = accepted_values(context, &declaration)?;
            let mut present: bool = false;
            for audit in &audits {
                if audit.eq(&generated)? {
                    present = true;
                    break;
                }
            }
            if !present {
                audits.push(generated);
            }
        }
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        for field in KEPT_COLUMN_FIELDS {
            fields.set_item(field, column.getattr(field)?)?;
        }
        fields.set_item(TYPE_FIELD, declaration.getattr(SCALAR_TYPE_ATTRIBUTE)?)?;
        fields.set_item(AUDITS_FIELD, PyTuple::new(py, audits)?)?;
        resolved_columns.push(context.contracts.schema_column.call((), Some(&fields))?);
    }
    let usages: Vec<Bound<'py, PyAny>> =
        generated_usages(context, declarations, consumer, &resolved)?;
    Ok(EnumColumns {
        columns: PyTuple::new(py, resolved_columns)?,
        declarations: resolved,
        usages,
    })
}

/// The schema row the retained facts are read from, as `_schema_row` builds it.
pub(crate) fn schema_row(
    columns: &Bound<'_, PyTuple>,
    (audit_count, model_path): (usize, &Bound<'_, PyAny>),
    families: &[Bound<'_, PyAny>],
    switches: (bool, bool),
) -> PyResult<SchemaPy> {
    let mut column_rows: Vec<SchemaColumnPy> = Vec::with_capacity(columns.len());
    for column in columns.iter() {
        let location: Bound<'_, PyAny> = column.getattr(LOCATION_FIELD)?;
        let declared_outside: bool =
            !location.is_none() && location.getattr(PATH_FIELD)?.ne(model_path)?;
        column_rows.push((
            column.getattr(NAME_FIELD)?.extract()?,
            column.getattr(TYPE_FIELD)?.extract()?,
            column.getattr(NULLABLE_FIELD)?.extract()?,
            u32::try_from(column.getattr(AUDITS_FIELD)?.len()?).unwrap_or(u32::MAX),
            declared_outside,
        ));
    }
    let mut family_rows: Vec<DynamicFamilyPy> = Vec::with_capacity(families.len());
    for family in families {
        let name: Bound<'_, PyAny> = family.getattr(NAME_FIELD)?;
        family_rows.push((
            name.call_method0(CASEFOLD_METHOD)?.extract()?,
            name.extract()?,
            family.getattr(PIVOT_COLUMN_FIELD)?.extract()?,
            family.getattr(VALUE_COLUMN_FIELD)?.extract()?,
            family.getattr(AGGREGATE_FIELD)?.extract()?,
            family.getattr(TYPE_FIELD)?.extract()?,
            family.getattr(NAME_PATTERN_FIELD)?.extract()?,
        ));
    }
    Ok((
        u32::try_from(audit_count).unwrap_or(u32::MAX),
        column_rows,
        family_rows,
        switches,
    ))
}

fn accepted_values<'py>(
    context: &LoopContext<'_, 'py>,
    declaration: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = declaration.py();
    let mut members: Vec<Bound<'py, PyAny>> = Vec::new();
    for member in declaration.getattr(MEMBERS_FIELD)?.try_iter()? {
        members.push(member?.getattr(VALUE_FIELD)?);
    }
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item(VALUES_ARGUMENT, PyTuple::new(py, members)?)?;
    keywords(
        &context.contracts.schema_audit_instance,
        &[
            (
                DEFINITION_NAME_FIELD,
                ACCEPTED_VALUES_AUDIT.into_pyobject_any(py)?,
            ),
            (ARGUMENTS_FIELD, arguments.into_any()),
        ],
    )
}

fn generated_usages<'py>(
    context: &LoopContext<'_, 'py>,
    declarations: &Bound<'py, PyAny>,
    consumer: &Bound<'py, PyAny>,
    resolved: &Bound<'py, PyDict>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let visibility: Bound<'py, PyDict> = declarations
        .getattr(ENUM_VISIBILITY_ATTRIBUTE)?
        .downcast_into()?;
    let mut usages: Vec<Bound<'py, PyAny>> = Vec::new();
    for declaration in resolved.values() {
        let Some(records) = visibility.get_item(declaration.getattr(NAME_FIELD)?)? else {
            continue;
        };
        for record in records.try_iter()? {
            let record: Bound<'py, PyAny> = record?;
            usages.push(keywords(
                &context.classes.usage_record,
                &[
                    (CONSUMER_FIELD, consumer.clone()),
                    (DECLARATION_FIELD, record.getattr(DECLARATION_FIELD)?),
                    (KIND_FIELD, context.classes.generated_usage.clone()),
                    (THROUGH_FIELD, record.getattr(THROUGH_FIELD)?),
                ],
            )?);
        }
    }
    Ok(usages)
}

fn keywords<'py>(
    class: &Bound<'py, PyAny>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: Bound<'py, PyDict> = PyDict::new(class.py());
    for (key, value) in fields {
        arguments.set_item(*key, value)?;
    }
    class.call((), Some(&arguments))
}

/// `into_pyobject` for any value, as a `PyAny`.
trait IntoPyAny<'py> {
    fn into_pyobject_any(self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>>;
}

impl<'py, T> IntoPyAny<'py> for T
where
    T: pyo3::IntoPyObject<'py>,
    PyErr: From<T::Error>,
{
    fn into_pyobject_any(self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        Ok(self.into_pyobject(py)?.into_any().into_bound())
    }
}
