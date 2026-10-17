//! Parsed MODEL header columns and audits built into the Python contract objects.

use std::sync::OnceLock;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyTuple};
use pyo3::{FromPyObject, IntoPyObject};
use sqlbuild_model_config::header_metadata::models::{
    ParsedAudit, ParsedColumn, ParsedThresholds, ThresholdBound,
};

use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::records::construct::record_class;
use crate::bindings::_helpers::records::fields::all_specs;
use crate::bindings::_helpers::records::fields::field;
use crate::bindings::_helpers::records::ids::RecordId;

/// Native column fields; a Python record is constructed only for public consumers.
pub(crate) struct HeaderColumn {
    values: Option<[Py<PyAny>; 8]>,
    class: Py<PyAny>,
    projection: PyOnceLock<Py<PyAny>>,
}

impl HeaderColumn {
    pub(crate) fn replaced<'py>(
        class: &Bound<'py, PyAny>,
        values: [Bound<'py, PyAny>; 8],
        keyword_order: [usize; 8],
    ) -> PyResult<Self> {
        if class.is(&record_class(class.py(), RecordId::SchemaColumn)?) {
            return Self::new(class, values);
        }
        let fields = PyDict::new(class.py());
        for index in keyword_order {
            fields.set_item(SCHEMA_COLUMN_FIELDS[index], &values[index])?;
        }
        Self::from_python(class.call((), Some(&fields))?)
    }

    pub(crate) fn field<'py>(&self, py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
        let Some(values) = &self.values else {
            return field(&self.project(py)?, name);
        };
        let index = SCHEMA_COLUMN_FIELDS
            .iter()
            .position(|field| *field == name)
            .ok_or_else(|| PyRuntimeError::new_err("unknown column field"))?;
        Ok(values[index].bind(py).clone())
    }

    pub(crate) fn project<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.projection
            .get_or_try_init(py, || {
                let values = self
                    .values
                    .as_ref()
                    .ok_or_else(|| PyRuntimeError::new_err("missing column projection"))?;
                contract_object(
                    self.class.bind(py),
                    values.each_ref().map(|value| value.bind(py).clone()),
                )
                .map(Bound::unbind)
            })
            .map(|value| value.bind(py).clone())
    }

    pub(crate) fn from_python(value: Bound<'_, PyAny>) -> PyResult<Self> {
        let py = value.py();
        let projection = PyOnceLock::new();
        let class = value.get_type().into_any().unbind();
        let _ = projection.set(py, value.unbind());
        Ok(Self {
            values: None,
            class,
            projection,
        })
    }

    pub(crate) fn new<'py>(
        class: &Bound<'py, PyAny>,
        values: [Bound<'py, PyAny>; 8],
    ) -> PyResult<Self> {
        if !class.is(&record_class(class.py(), RecordId::SchemaColumn)?) {
            return Self::from_python(contract_object(class, values)?);
        }
        checked_field_orders()?;
        Ok(Self {
            values: Some(values.map(Bound::unbind)),
            class: class.clone().unbind(),
            projection: PyOnceLock::new(),
        })
    }
}

/// Retained native columns and their shared, lazy public tuple.
pub(crate) struct HeaderColumns {
    pub(crate) specs: Vec<HeaderColumn>,
    projection: PyOnceLock<Py<PyTuple>>,
}

impl HeaderColumns {
    pub(crate) fn new(specs: Vec<HeaderColumn>) -> Self {
        Self {
            specs,
            projection: PyOnceLock::new(),
        }
    }

    pub(crate) fn project<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        self.projection
            .get_or_try_init(py, || {
                let columns = self
                    .specs
                    .iter()
                    .map(|column| column.project(py))
                    .collect::<PyResult<Vec<_>>>()?;
                PyTuple::new(py, columns).map(Bound::unbind)
            })
            .map(|value| value.bind(py).clone())
    }
}

/// `SchemaColumn` fields in declaration order, the order its objects are built positionally in.
const SCHEMA_COLUMN_FIELDS: [&str; 8] = [
    "name",
    "type",
    "nullable",
    "description",
    "meta",
    "audits",
    "location",
    "migrate_from",
];
/// `SchemaAuditInstance` fields in declaration order.
const AUDIT_INSTANCE_FIELDS: [&str; 11] = [
    "definition_name",
    "arguments",
    "name",
    "description",
    "severity",
    "run_scope",
    "always_run",
    "thresholds",
    "minimum_samples",
    "evidence_limit",
    "location",
];
/// `MeasurementThresholds` fields in declaration order.
const THRESHOLDS_FIELDS: [&str; 2] = ["warn", "error"];
/// `MeasurementThresholdBound` fields in declaration order.
const THRESHOLD_BOUND_FIELDS: [&str; 4] = ["operator", "limit", "lower", "upper"];
/// Each positionally built record with the field order its values are given in.
const POSITIONAL_RECORDS: [(&str, &[&str]); 4] = [
    ("SchemaColumn", &SCHEMA_COLUMN_FIELDS),
    ("SchemaAuditInstance", &AUDIT_INSTANCE_FIELDS),
    ("MeasurementThresholds", &THRESHOLDS_FIELDS),
    ("MeasurementThresholdBound", &THRESHOLD_BOUND_FIELDS),
];

/// The Python classes the parsed metadata becomes, read from a Python mapping.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct ContractClasses<'py> {
    pub(crate) schema_column: Bound<'py, PyAny>,
    pub(crate) schema_audit_instance: Bound<'py, PyAny>,
    pub(crate) schema_dynamic_column_family: Bound<'py, PyAny>,
    pub(crate) source_location: Bound<'py, PyAny>,
    measurement_thresholds: Bound<'py, PyAny>,
    measurement_threshold_bound: Bound<'py, PyAny>,
    severities: Bound<'py, PyDict>,
    threshold_operators: Bound<'py, PyDict>,
}

pub(crate) fn column_tuple<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    parsed: &[ParsedColumn<PyNode<'py>>],
    locations: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(py, schema_columns(py, classes, parsed, locations)?)
}

/// The parsed columns as `SchemaColumn` objects, in declaration order.
pub(crate) fn schema_columns<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    parsed: &[ParsedColumn<PyNode<'py>>],
    locations: &Bound<'py, PyDict>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut columns: Vec<Bound<'py, PyAny>> = Vec::with_capacity(parsed.len());
    for column in parsed {
        columns.push(schema_column(py, classes, column, locations)?);
    }
    Ok(columns)
}

pub(crate) fn audit_tuple<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    parsed: &[ParsedAudit<PyNode<'py>>],
) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(py, audit_instances(py, classes, parsed)?)
}

/// The parsed audits as `SchemaAuditInstance` objects without a location, in order.
pub(crate) fn audit_instances<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    parsed: &[ParsedAudit<PyNode<'py>>],
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let no_location: Bound<'py, PyAny> = py.None().into_bound(py);
    let mut audits: Vec<Bound<'py, PyAny>> = Vec::with_capacity(parsed.len());
    for audit in parsed {
        audits.push(audit_instance(py, classes, audit, &no_location)?);
    }
    Ok(audits)
}

/// `audit.name or audit.definition_name` of the instance `audit` builds.
pub(crate) fn parsed_audit_identity(audit: &ParsedAudit<PyNode<'_>>) -> PyResult<String> {
    if let Some(name) = &audit.name
        && name.0.is_truthy()?
    {
        return name.0.extract();
    }
    audit.definition_name.0.extract()
}

/// `class(*values)`: the same record as keywords bind, given in `POSITIONAL_RECORDS` order.
fn contract_object<'py, const N: usize>(
    class: &Bound<'py, PyAny>,
    values: [Bound<'py, PyAny>; N],
) -> PyResult<Bound<'py, PyAny>> {
    checked_field_orders()?;
    class.call1(PyTuple::new(class.py(), values)?)
}

/// Fail when a positionally built record no longer declares its fields in the expected order.
fn checked_field_orders() -> PyResult<()> {
    static MISMATCH: OnceLock<Option<&'static str>> = OnceLock::new();
    match MISMATCH.get_or_init(mismatched_record) {
        Some(record) => Err(PyRuntimeError::new_err(format!(
            "native record {record} does not declare the fields header metadata builds it with"
        ))),
        None => Ok(()),
    }
}

/// The first positionally built record whose registered fields differ from its expected order.
fn mismatched_record() -> Option<&'static str> {
    for (record, fields) in POSITIONAL_RECORDS {
        let mut declared: bool = false;
        for spec in all_specs() {
            if spec.name == record {
                declared = spec.fields.len() == fields.len()
                    && spec
                        .fields
                        .iter()
                        .zip(fields)
                        .all(|(field, expected)| field.name == *expected);
                break;
            }
        }
        if !declared {
            return Some(record);
        }
    }
    None
}

fn optional<'py>(py: Python<'py>, value: Option<&PyNode<'py>>) -> Bound<'py, PyAny> {
    value.map_or_else(|| py.None().into_bound(py), |node| node.0.clone())
}

fn schema_column<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    column: &ParsedColumn<PyNode<'py>>,
    locations: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    native_schema_column(py, classes, column, locations)?.project(py)
}

pub(crate) fn native_schema_column<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    column: &ParsedColumn<PyNode<'py>>,
    locations: &Bound<'py, PyDict>,
) -> PyResult<HeaderColumn> {
    let location = locations
        .get_item(&column.name.0)?
        .unwrap_or_else(|| py.None().into_bound(py));
    let audits = column
        .audits
        .iter()
        .map(|audit| audit_instance(py, classes, audit, &location))
        .collect::<PyResult<Vec<_>>>()?;
    HeaderColumn::new(
        &classes.schema_column,
        [
            column.name.0.clone(),
            optional(py, column.column_type.as_ref()),
            optional(py, column.nullable.as_ref()),
            optional(py, column.description.as_ref()),
            PyDict::new(py).into_any(),
            PyTuple::new(py, audits)?.into_any(),
            location,
            optional(py, column.migrate_from.as_ref()),
        ],
    )
}

fn audit_instance<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    audit: &ParsedAudit<PyNode<'py>>,
    location: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments = PyDict::new(py);
    for (key, value) in &audit.arguments {
        arguments.set_item(&key.0, &value.0)?;
    }
    let severity = match &audit.severity {
        Some(severity) => classes
            .severities
            .get_item(&severity.0)?
            .unwrap_or_else(|| py.None().into_bound(py)),
        None => py.None().into_bound(py),
    };
    let always_run = audit.always_run.as_ref().map_or_else(
        || PyBool::new(py, false).to_owned().into_any(),
        |node| node.0.clone(),
    );
    contract_object(
        &classes.schema_audit_instance,
        [
            audit.definition_name.0.clone(),
            arguments.into_any(),
            optional(py, audit.name.as_ref()),
            optional(py, audit.description.as_ref()),
            severity,
            optional(py, audit.run_scope.as_ref()),
            always_run,
            thresholds(py, classes, audit.thresholds.as_ref())?,
            optional(py, audit.minimum_samples.as_ref()),
            optional(py, audit.evidence_limit.as_ref()),
            location.clone(),
        ],
    )
}

/// `MeasurementThresholds` of `parsed`, or `None`.
pub(crate) fn thresholds<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    parsed: Option<&ParsedThresholds>,
) -> PyResult<Bound<'py, PyAny>> {
    let Some(parsed) = parsed else {
        return Ok(py.None().into_bound(py));
    };
    contract_object(
        &classes.measurement_thresholds,
        [
            threshold_bound(py, classes, parsed.warn)?,
            threshold_bound(py, classes, parsed.error)?,
        ],
    )
}

fn threshold_bound<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    bound: Option<ThresholdBound>,
) -> PyResult<Bound<'py, PyAny>> {
    let Some(bound) = bound else {
        return Ok(py.None().into_bound(py));
    };
    let (operator, limit, lower, upper) = match bound {
        ThresholdBound::Below(limit) => ("below", Some(limit), None, None),
        ThresholdBound::Above(limit) => ("above", Some(limit), None, None),
        ThresholdBound::Outside(lower, upper) => ("outside", None, Some(lower), Some(upper)),
    };
    let operator = classes
        .threshold_operators
        .get_item(operator)?
        .unwrap_or_else(|| py.None().into_bound(py));
    contract_object(
        &classes.measurement_threshold_bound,
        [
            operator,
            limit.into_pyobject(py)?.into_any(),
            lower.into_pyobject(py)?.into_any(),
            upper.into_pyobject(py)?.into_any(),
        ],
    )
}
