//! Convert existing planner contracts for origin compatibility checks.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::analysis::model_reads::inferred_rows;
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyTuple, PyTupleMethods};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_migrations::main::compatibility_findings::compatibility_findings;
use sqlbuild_analysis::planner_migrations::models::CompatibilityFinding;

fn config(model: &Bound<'_, PyAny>, key: &str) -> PyResult<Option<String>> {
    model
        .getattr("config")?
        .getattr("values")?
        .call_method1("get", (key,))?
        .extract()
}

fn blocking<'py>(
    py: Python<'py>,
    arguments: &KeywordArguments<'py>,
    snapshot: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    let model = arguments.value("model")?;
    let policy = if snapshot {
        config(&model, "snapshot_schema_change")?
            .filter(|value| !value.is_empty())
            .unwrap_or(
                arguments
                    .value("snapshots_config")?
                    .getattr("schema_change")?
                    .extract()?,
            )
    } else {
        config(&model, "on_schema_change")?
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "append_new_columns".to_owned())
    };
    registry::class(
        py,
        if snapshot {
            RecordId::SnapshotSchemaChangePolicy
        } else {
            RecordId::OnSchemaChange
        },
    )?
    .call1((&policy,))?;
    let mut findings: Vec<CompatibilityFinding> = Vec::new();
    for finding in arguments.value("findings")?.try_iter()? {
        let finding = finding?;
        findings.push(CompatibilityFinding {
            kind: finding.getattr("kind")?.extract()?,
            column_name: finding.getattr("column_name")?.extract()?,
            expected_type: finding.getattr("expected_type")?.extract()?,
            actual_type: finding.getattr("actual_type")?.extract()?,
        });
    }
    let dialect: Option<String> = arguments.value("dialect")?.extract()?;
    PyTuple::new(
        py,
        compatibility_findings(
            &findings,
            (&policy, snapshot),
            dialect.as_deref().unwrap_or("generic"),
        )
        .map_err(PyValueError::new_err)?,
    )
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn migration_incremental_blocking_findings<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments = KeywordArguments::read(
        py,
        "migration_incremental_blocking_findings",
        options,
        (&["model", "findings", "dialect"], &[]),
    )?;
    blocking(py, &arguments, false)
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn migration_snapshot_blocking_findings<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments = KeywordArguments::read(
        py,
        "migration_snapshot_blocking_findings",
        options,
        (&["model", "findings", "dialect", "snapshots_config"], &[]),
    )?;
    blocking(py, &arguments, true)
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn check_migration_compatibility<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments = KeywordArguments::read(
        py,
        "check_migration_compatibility",
        options,
        (
            &[
                "model",
                "origin_relation",
                "origin_columns",
                "sql_analysis_enabled",
                "column_dialect",
                "snapshots_config",
            ],
            &[],
        ),
    )?;
    let model = arguments.value("model")?;
    let relation = arguments.value("origin_relation")?;
    let relation_type: String = relation.getattr("relation_type")?.extract()?;
    if relation_type.to_uppercase().contains("VIEW") {
        return result(
            py,
            "incompatible",
            PyTuple::new(
                py,
                ["origin relation is a view; only tables carry migratable history"],
            )?,
        );
    }
    let relations = PyDict::new(py);
    relations.set_item(model_reads::name_object(&model)?, relation)?;
    let columns = PyDict::new(py);
    columns.set_item(
        model_reads::name_object(&model)?,
        arguments.value("origin_columns")?,
    )?;
    let snapshot = call_with(
        &registry::class(py, RecordId::WarehouseSnapshot)?,
        &[
            ("existing_relations", relations.into_any()),
            ("existing_columns", columns.into_any()),
            ("column_dialect", arguments.value("column_dialect")?),
        ],
    )?;
    let change = call_with(
        &registry::native(py, NativeAttr::DetectModelChanges)?,
        &[
            ("model", model.clone()),
            ("snapshot", snapshot),
            (
                "sql_analysis_enabled",
                arguments.value("sql_analysis_enabled")?,
            ),
            (
                "query_change_tracking",
                false.into_pyobject(py)?.to_owned().into_any(),
            ),
            (
                "full_refresh",
                false.into_pyobject(py)?.to_owned().into_any(),
            ),
        ],
    )?;
    let schema = model.getattr("schema_entry")?;
    let mut has_columns = inferred_rows(&model)?.is_some_and(|rows| !rows.is_empty());
    if !schema.is_none() {
        for column in schema.getattr("columns")?.try_iter()? {
            has_columns |= !column?.getattr("type")?.is_none();
        }
    }
    if !has_columns {
        return result(py, "not_checked", PyTuple::empty(py));
    }
    let snapshot = config(&model, "materialized")?.as_deref() == Some("snapshot");
    let options = PyDict::new(py);
    options.set_item("model", model)?;
    options.set_item("findings", change.getattr("schema_findings")?)?;
    options.set_item("dialect", arguments.value("column_dialect")?)?;
    let findings = if snapshot {
        options.set_item("snapshots_config", arguments.value("snapshots_config")?)?;
        migration_snapshot_blocking_findings(py, Some(options))?
    } else {
        migration_incremental_blocking_findings(py, Some(options))?
    };
    result(
        py,
        if findings.is_empty() {
            "compatible"
        } else {
            "incompatible"
        },
        findings,
    )
}

fn result<'py>(
    py: Python<'py>,
    status: &str,
    findings: Bound<'py, PyTuple>,
) -> PyResult<Bound<'py, PyAny>> {
    let status = registry::class(py, RecordId::MigrationCompatibility)?.call1((status,))?;
    call_with(
        &registry::class(py, RecordId::MigrationCompatibilityResult)?,
        &[("status", status), ("findings", findings.into_any())],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(check_migration_compatibility, module)?)?;
    module.add_function(wrap_pyfunction!(
        migration_incremental_blocking_findings,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        migration_snapshot_blocking_findings,
        module
    )?)
}
