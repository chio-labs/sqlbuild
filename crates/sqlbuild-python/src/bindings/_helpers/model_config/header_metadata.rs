//! MODEL header columns and audits parsed natively into the Python contract objects.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyTuple};
use pyo3::{FromPyObject, IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_model_config::header_metadata::models::{
    ParsedAudit, ParsedColumn, ParsedThresholds, ThresholdBound,
};

use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::config_errors::native_config_error;

/// The Python classes the parsed metadata becomes, read from a Python mapping.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ContractClasses<'py> {
    schema_column: Bound<'py, PyAny>,
    schema_audit_instance: Bound<'py, PyAny>,
    measurement_thresholds: Bound<'py, PyAny>,
    measurement_threshold_bound: Bound<'py, PyAny>,
    severities: Bound<'py, PyDict>,
    threshold_operators: Bound<'py, PyDict>,
    allocate: Bound<'py, PyAny>,
}

/// A model's columns and audits as contract tuples or errors; no audits after a column error.
#[pyfunction]
fn parse_model_header_metadata<'py>(
    py: Python<'py>,
    columns: Bound<'py, PyAny>,
    audits: Bound<'py, PyAny>,
    locations: Bound<'py, PyDict>,
    path: &str,
    classes: ContractClasses<'py>,
) -> PyResult<Bound<'py, PyTuple>> {
    let metadata = parse_header_metadata(&PyNode(columns), &PyNode(audits), path);
    let columns = match metadata.columns {
        Err(error) => {
            return (native_config_error(py, error)?, py.None()).into_pyobject(py);
        }
        Ok(columns) => column_tuple(py, &classes, &columns, &locations)?,
    };
    match metadata.audits {
        Err(error) => (columns, native_config_error(py, error)?).into_pyobject(py),
        Ok(audits) => (columns, audit_tuple(py, &classes, &audits)?).into_pyobject(py),
    }
}

fn column_tuple<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    parsed: &[ParsedColumn<PyNode<'py>>],
    locations: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyTuple>> {
    let mut columns: Vec<Bound<'py, PyAny>> = Vec::with_capacity(parsed.len());
    for column in parsed {
        columns.push(schema_column(py, classes, column, locations)?);
    }
    PyTuple::new(py, columns)
}

fn audit_tuple<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    parsed: &[ParsedAudit<PyNode<'py>>],
) -> PyResult<Bound<'py, PyTuple>> {
    let no_location: Bound<'py, PyAny> = py.None().into_bound(py);
    let mut audits: Vec<Bound<'py, PyAny>> = Vec::with_capacity(parsed.len());
    for audit in parsed {
        audits.push(audit_instance(py, classes, audit, &no_location)?);
    }
    PyTuple::new(py, audits)
}

/// Build a frozen contract dataclass the way `copy` does: allocate, then fill its `__dict__`.
fn contract_object<'py>(
    allocate: &Bound<'py, PyAny>,
    class: &Bound<'py, PyAny>,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    let object = allocate.call1((class,))?;
    let attributes = object.getattr("__dict__")?.downcast_into::<PyDict>()?;
    for (name, value) in fields {
        attributes.set_item(name, value)?;
    }
    Ok(object)
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
    let location = locations
        .get_item(&column.name.0)?
        .unwrap_or_else(|| py.None().into_bound(py));
    let audits = column
        .audits
        .iter()
        .map(|audit| audit_instance(py, classes, audit, &location))
        .collect::<PyResult<Vec<_>>>()?;
    contract_object(
        &classes.allocate,
        &classes.schema_column,
        &[
            ("name", column.name.0.clone()),
            ("type", optional(py, column.column_type.as_ref())),
            ("nullable", optional(py, column.nullable.as_ref())),
            ("description", optional(py, column.description.as_ref())),
            ("meta", PyDict::new(py).into_any()),
            ("audits", PyTuple::new(py, audits)?.into_any()),
            ("location", location),
            ("migrate_from", optional(py, column.migrate_from.as_ref())),
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
        &classes.allocate,
        &classes.schema_audit_instance,
        &[
            ("definition_name", audit.definition_name.0.clone()),
            ("arguments", arguments.into_any()),
            ("name", optional(py, audit.name.as_ref())),
            ("description", optional(py, audit.description.as_ref())),
            ("severity", severity),
            ("run_scope", optional(py, audit.run_scope.as_ref())),
            ("always_run", always_run),
            (
                "thresholds",
                thresholds(py, classes, audit.thresholds.as_ref())?,
            ),
            (
                "minimum_samples",
                optional(py, audit.minimum_samples.as_ref()),
            ),
            (
                "evidence_limit",
                optional(py, audit.evidence_limit.as_ref()),
            ),
            ("location", location.clone()),
        ],
    )
}

fn thresholds<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    parsed: Option<&ParsedThresholds>,
) -> PyResult<Bound<'py, PyAny>> {
    let Some(parsed) = parsed else {
        return Ok(py.None().into_bound(py));
    };
    contract_object(
        &classes.allocate,
        &classes.measurement_thresholds,
        &[
            ("warn", threshold_bound(py, classes, parsed.warn)?),
            ("error", threshold_bound(py, classes, parsed.error)?),
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
        &classes.allocate,
        &classes.measurement_threshold_bound,
        &[
            ("operator", operator),
            ("limit", limit.into_pyobject(py)?.into_any()),
            ("lower", lower.into_pyobject(py)?.into_any()),
            ("upper", upper.into_pyobject(py)?.into_any()),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_model_header_metadata, module)?)?;
    Ok(())
}
