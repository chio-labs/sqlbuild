//! MODEL header columns and audits parsed natively into the Python contract objects.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyString, PyTuple};
use pyo3::{FromPyObject, IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_model_config::header_metadata::main::parse_header_metadata::parse_header_metadata;
use sqlbuild_model_config::header_metadata::models::{
    HeaderMetadata, HeaderMetadataDeferral, ParsedAudit, ParsedColumn,
};

use crate::bindings::_helpers::model_config::authored_nodes::PyNode;

/// A model's `(columns, audits)` tuples, or the outcome name `invalid` or `unsupported`.
type ParsedMetadataRow = Py<PyAny>;

const INVALID_OUTCOME: &str = "invalid";
const UNSUPPORTED_OUTCOME: &str = "unsupported";

/// The Python classes the parsed metadata becomes, read from a Python mapping.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ContractClasses<'py> {
    schema_column: Bound<'py, PyAny>,
    schema_audit_instance: Bound<'py, PyAny>,
    severities: Bound<'py, PyDict>,
    allocate: Bound<'py, PyAny>,
}

/// One model's authored `columns` and `audits` values and its column locations.
#[derive(FromPyObject)]
struct HeaderMetadataRequest<'py>(Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyDict>);

/// Return each model's `(columns, audits)` contract tuples, or why Python must parse it.
#[pyfunction]
fn parse_model_header_metadata<'py>(
    py: Python<'py>,
    requests: Vec<HeaderMetadataRequest<'py>>,
    classes: ContractClasses<'py>,
) -> PyResult<Vec<ParsedMetadataRow>> {
    let mut rows: Vec<ParsedMetadataRow> = Vec::with_capacity(requests.len());
    for HeaderMetadataRequest(columns, audits, locations) in requests {
        rows.push(
            match parse_header_metadata(&PyNode(columns), &PyNode(audits)) {
                Ok(metadata) => metadata_row(py, &classes, &metadata, &locations)?,
                Err(HeaderMetadataDeferral::Invalid) => {
                    PyString::new(py, INVALID_OUTCOME).into_any().unbind()
                }
                Err(HeaderMetadataDeferral::Unsupported) => {
                    PyString::new(py, UNSUPPORTED_OUTCOME).into_any().unbind()
                }
            },
        );
    }
    Ok(rows)
}

fn metadata_row<'py>(
    py: Python<'py>,
    classes: &ContractClasses<'py>,
    metadata: &HeaderMetadata<PyNode<'py>>,
    locations: &Bound<'py, PyDict>,
) -> PyResult<ParsedMetadataRow> {
    let no_location: Bound<'py, PyAny> = py.None().into_bound(py);
    let mut columns: Vec<Bound<'py, PyAny>> = Vec::with_capacity(metadata.columns.len());
    for column in &metadata.columns {
        columns.push(schema_column(py, classes, column, locations)?);
    }
    let mut audits: Vec<Bound<'py, PyAny>> = Vec::with_capacity(metadata.audits.len());
    for audit in &metadata.audits {
        audits.push(audit_instance(py, classes, audit, &no_location)?);
    }
    Ok((PyTuple::new(py, columns)?, PyTuple::new(py, audits)?)
        .into_pyobject(py)?
        .into_any()
        .unbind())
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
            ("thresholds", py.None().into_bound(py)),
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

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(parse_model_header_metadata, module)?)?;
    Ok(())
}
