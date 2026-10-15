//! The Python classes native header and YAML parsing build contract objects as.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::sync::PyOnceLock;
use pyo3::types::{PyDict, PyDictMethods};

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const AUDITING_MODELS_MODULE: &str = "sqlbuild.compiler.auditing.models";
const AUDITING_TYPES_MODULE: &str = "sqlbuild.compiler.auditing.types";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild.spec.contracts.models";
const CONTRACT_TYPES_MODULE: &str = "sqlbuild.spec.contracts.types";
const DLT_MODELS_MODULE: &str = "sqlbuild.integrations.dlt.models";
const INGESTR_MODELS_MODULE: &str = "sqlbuild.integrations.ingestr.models";
const CONTRACT_CLASSES: [(&str, &str, &str); 6] = [
    ("schema_column", CONTRACT_MODELS_MODULE, "SchemaColumn"),
    (
        "schema_audit_instance",
        CONTRACT_MODELS_MODULE,
        "SchemaAuditInstance",
    ),
    (
        "schema_dynamic_column_family",
        CONTRACT_MODELS_MODULE,
        "SchemaDynamicColumnFamily",
    ),
    ("source_location", CONTRACT_MODELS_MODULE, "SourceLocation"),
    (
        "measurement_thresholds",
        AUDITING_MODELS_MODULE,
        "MeasurementThresholds",
    ),
    (
        "measurement_threshold_bound",
        AUDITING_MODELS_MODULE,
        "MeasurementThresholdBound",
    ),
];
const YAML_ENTRY_CLASSES: [(&str, &str, &str); 13] = [
    (
        "schema_seed_entry",
        CONTRACT_MODELS_MODULE,
        "SchemaSeedEntry",
    ),
    (
        "seed_csv_settings",
        CONTRACT_MODELS_MODULE,
        "SeedCsvSettings",
    ),
    ("source_entry", CONTRACT_MODELS_MODULE, "SourceEntry"),
    (
        "source_column_entry",
        CONTRACT_MODELS_MODULE,
        "SourceColumnEntry",
    ),
    (
        "source_freshness_config",
        CONTRACT_MODELS_MODULE,
        "SourceFreshnessConfig",
    ),
    (
        "source_freshness_age_policy",
        CONTRACT_MODELS_MODULE,
        "SourceFreshnessAgePolicy",
    ),
    (
        "integration_loader_config",
        CONTRACT_MODELS_MODULE,
        "IntegrationLoaderConfig",
    ),
    (
        "ingestr_source_config",
        INGESTR_MODELS_MODULE,
        "IngestrSourceConfig",
    ),
    ("dlt_source_config", DLT_MODELS_MODULE, "DltSourceConfig"),
    (
        "dlt_resource_config",
        DLT_MODELS_MODULE,
        "DltResourceConfig",
    ),
    (
        "source_write_strategy",
        CONTRACT_TYPES_MODULE,
        "SourceWriteStrategy",
    ),
    (
        "source_freshness_strategy",
        CONTRACT_TYPES_MODULE,
        "SourceFreshnessStrategy",
    ),
    (
        "source_freshness_value_kind",
        CONTRACT_TYPES_MODULE,
        "SourceFreshnessValueKind",
    ),
];

static CONTRACT_CLASS_TABLE: PyOnceLock<Py<PyDict>> = PyOnceLock::new();
static YAML_ENTRY_CLASS_TABLE: PyOnceLock<Py<PyDict>> = PyOnceLock::new();

/// The contract classes native header parsing builds columns and audits as.
pub(crate) fn contract_classes(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    CONTRACT_CLASS_TABLE
        .get_or_try_init(py, || built_contract_classes(py).map(Bound::unbind))
        .map(|classes| classes.bind(py).clone())
}

/// The classes parsed seed and source declarations become.
pub(crate) fn yaml_entry_classes(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    YAML_ENTRY_CLASS_TABLE
        .get_or_try_init(py, || built_yaml_entry_classes(py).map(Bound::unbind))
        .map(|classes| classes.bind(py).clone())
}

fn built_contract_classes(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let classes: Bound<'_, PyDict> = PyDict::new(py);
    for (key, module, name) in CONTRACT_CLASSES {
        classes.set_item(key, imported(py, module, name)?)?;
    }
    classes.set_item(
        "severities",
        members_by_value(&imported(py, AUDITING_TYPES_MODULE, "AuditSeverity")?)?,
    )?;
    classes.set_item(
        "threshold_operators",
        members_by_value(&imported(py, AUDITING_TYPES_MODULE, "ThresholdOperator")?)?,
    )?;
    classes.set_item(
        "allocate",
        imported(py, "builtins", "object")?.getattr("__new__")?,
    )?;
    Ok(classes)
}

fn built_yaml_entry_classes(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let classes: Bound<'_, PyDict> = PyDict::new(py);
    classes.set_item("contracts", contract_classes(py)?)?;
    for (key, module, name) in YAML_ENTRY_CLASSES {
        classes.set_item(key, imported(py, module, name)?)?;
    }
    Ok(classes)
}

/// `{member.value: member for member in enum}`.
fn members_by_value<'py>(enumeration: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let members: Bound<'py, PyDict> = PyDict::new(enumeration.py());
    for member in enumeration.try_iter()? {
        let member: Bound<'py, PyAny> = member?;
        members.set_item(member.getattr("value")?, member)?;
    }
    Ok(members)
}
