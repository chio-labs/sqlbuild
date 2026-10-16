//! Convert existing planner contracts for origin compatibility checks.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::analysis::model_reads::inferred_rows;
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, call_with};
use crate::bindings::_helpers::planner_migrations::models::{
    CompatibilityCheck, MigrationCompatibilityResult,
};
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

/// The schema findings that block migrating one model's history; `snapshots_config` is given for snapshots.
fn blocking<'py>(
    (model, findings_in): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    dialect: &Bound<'py, PyAny>,
    snapshots_config: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py = model.py();
    let snapshot = snapshots_config.is_some();
    let policy = if let Some(snapshots_config) = snapshots_config {
        config(model, "snapshot_schema_change")?
            .filter(|value| !value.is_empty())
            .unwrap_or(snapshots_config.getattr("schema_change")?.extract()?)
    } else {
        config(model, "on_schema_change")?
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
    for finding in findings_in.try_iter()? {
        let finding = finding?;
        findings.push(CompatibilityFinding {
            kind: finding.getattr("kind")?.extract()?,
            column_name: finding.getattr("column_name")?.extract()?,
            expected_type: finding.getattr("expected_type")?.extract()?,
            actual_type: finding.getattr("actual_type")?.extract()?,
        });
    }
    let dialect: Option<String> = dialect.extract()?;
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
    blocking(
        (&arguments.value("model")?, &arguments.value("findings")?),
        &arguments.value("dialect")?,
        None,
    )
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
    blocking(
        (&arguments.value("model")?, &arguments.value("findings")?),
        &arguments.value("dialect")?,
        Some(&arguments.value("snapshots_config")?),
    )
}

/// Whether an origin relation's columns can carry the destination model's history.
pub(super) fn check_migration_compatibility<'py>(
    check: &CompatibilityCheck<'py>,
) -> PyResult<MigrationCompatibilityResult<'py>> {
    let py = check.model.py();
    let model = check.model.clone();
    let relation = check.origin_relation.clone();
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
        check.origin_columns.clone(),
    )?;
    let snapshot = call_with(
        &registry::class(py, RecordId::WarehouseSnapshot)?,
        &[
            ("existing_relations", relations.into_any()),
            ("existing_columns", columns.into_any()),
            ("column_dialect", check.column_dialect.clone()),
        ],
    )?;
    let change = call_with(
        &registry::native(py, NativeAttr::DetectModelChanges)?,
        &[
            ("model", model.clone()),
            ("snapshot", snapshot),
            ("sql_analysis_enabled", check.sql_analysis_enabled.clone()),
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
    let snapshots_config = check.snapshots_config.clone();
    let findings = blocking(
        (&model, &change.getattr("schema_findings")?),
        &check.column_dialect,
        snapshot.then_some(&snapshots_config),
    )?;
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
) -> PyResult<MigrationCompatibilityResult<'py>> {
    Ok(MigrationCompatibilityResult {
        status: registry::class(py, RecordId::MigrationCompatibility)?.call1((status,))?,
        findings: findings.into_any(),
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(
        migration_incremental_blocking_findings,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        migration_snapshot_blocking_findings,
        module
    )?)
}
