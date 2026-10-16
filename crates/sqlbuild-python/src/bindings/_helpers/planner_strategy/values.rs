//! Conversions between the planner's Python models and the native strategy rows.

use crate::bindings::_helpers::planner_changes::results::native_enum;
use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString};

use sqlbuild_analysis::planner_changes::models::{
    SchemaChangeKind, SchemaColumnSource, SchemaFindingRow,
};
use sqlbuild_analysis::planner_strategy::main::materialization_type::materialization_type;
use sqlbuild_analysis::planner_strategy::models::{
    ChangeFacts, MaterializationType, PlanChangeKind, WarningRow, WarningSeverity,
};

use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::records::registry;

const YML_SOURCE: &str = "yml";
const FULL_BACKFILL: &str = "full";
const FORWARD_ONLY_BACKFILL: &str = "forward";

/// `str(value)` of a Python string or string enum.
pub(crate) fn text(value: &Bound<'_, PyAny>) -> PyResult<String> {
    value.extract()
}

/// A string value, or `None` for `None` and anything that is not a string.
pub(crate) fn optional_string(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_instance_of::<PyString>() {
        return text(value).map(Some);
    }
    Ok(None)
}

/// `values.get(key)` of a model's config.
pub(crate) fn config_value<'py>(
    model: &Bound<'py, PyAny>,
    key: &str,
) -> PyResult<Bound<'py, PyAny>> {
    model
        .getattr("config")?
        .getattr("values")?
        .call_method1("get", (key,))
}

/// The materialization type of a model's `materialized` config.
pub(crate) fn model_materialization(model: &Bound<'_, PyAny>) -> PyResult<MaterializationType> {
    let materialized: Option<String> = optional_string(&config_value(model, "materialized")?)?;
    Ok(materialization_type(materialized.as_deref()))
}

/// The `MaterializationType` value of a materialization.
pub(crate) fn materialization_value(materialization: MaterializationType) -> &'static str {
    match materialization {
        MaterializationType::View => "view",
        MaterializationType::Table => "table",
        MaterializationType::Incremental => "incremental",
        MaterializationType::Snapshot => "snapshot",
        MaterializationType::Seed => "seed",
        MaterializationType::Custom => "custom",
    }
}

fn change_kind(value: &str) -> PlanChangeKind {
    match value {
        "first_run" => PlanChangeKind::FirstRun,
        "renamed" => PlanChangeKind::Renamed,
        "query_changed" => PlanChangeKind::QueryChanged,
        "function_changed" => PlanChangeKind::FunctionChanged,
        "config_changed" => PlanChangeKind::ConfigChanged,
        "schema_changed" => PlanChangeKind::SchemaChanged,
        _ => PlanChangeKind::NoChange,
    }
}

/// One `SchemaFinding` as a native row.
fn finding_row(finding: &Bound<'_, PyAny>) -> PyResult<SchemaFindingRow> {
    let kind: SchemaChangeKind = match text(&finding.getattr("kind")?)?.as_str() {
        "column_added" => SchemaChangeKind::ColumnAdded,
        "column_removed" => SchemaChangeKind::ColumnRemoved,
        _ => SchemaChangeKind::ColumnTypeChanged,
    };
    let source: SchemaColumnSource = if text(&finding.getattr("source")?)? == YML_SOURCE {
        SchemaColumnSource::Yml
    } else {
        SchemaColumnSource::SqlAnalysis
    };
    Ok(SchemaFindingRow {
        kind,
        column_name: text(&finding.getattr("column_name")?)?,
        source,
        expected_type: finding.getattr("expected_type")?.extract()?,
        actual_type: finding.getattr("actual_type")?.extract()?,
    })
}

/// A tuple of `SchemaFinding` values as native rows.
pub(crate) fn finding_rows(findings: &Bound<'_, PyAny>) -> PyResult<Vec<SchemaFindingRow>> {
    findings
        .try_iter()?
        .map(|finding| finding_row(&finding?))
        .collect()
}

/// The parts of a `ChangeDetectionResult` the strategy reads.
pub(crate) fn change_facts(change: &Bound<'_, PyAny>) -> PyResult<ChangeFacts> {
    let backfill: String = text(&change.getattr("backfill")?.getattr("action")?)?;
    Ok(ChangeFacts {
        kind: change_kind(&text(&change.getattr("change_kind")?)?),
        backfill_full: backfill == FULL_BACKFILL,
        backfill_forward_only: backfill == FORWARD_ONLY_BACKFILL,
        query_changed: change.getattr("query_changed")?.is_truthy()?,
        changed_functions: change
            .getattr("changed_functions")?
            .try_iter()?
            .map(|name| text(&name?))
            .collect::<PyResult<_>>()?,
        config_changed: change.getattr("config_changed")?.is_truthy()?,
        schema_findings: finding_rows(&change.getattr("schema_findings")?)?,
        recorded_build_relation_missing: change
            .getattr("recorded_build_relation_missing")?
            .is_truthy()?,
    })
}

/// `PlanWarning(model_name=..., severity=..., message=..., code=...)`.
pub(crate) fn plan_warning<'py>(
    model_name: &Bound<'py, PyAny>,
    row: WarningRow,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = model_name.py();
    let severity: &str = match row.severity {
        WarningSeverity::Error => "error",
        WarningSeverity::Warning => "warning",
        WarningSeverity::Info => "info",
    };
    call_with(
        &registry::class(py, RecordId::PlanWarning)?,
        &[
            ("model_name", model_name.clone()),
            (
                "severity",
                native_enum(py, RecordId::WarningSeverity, severity)?,
            ),
            ("message", PyString::new(py, &row.message).into_any()),
            ("code", row.code.into_pyobject(py)?.into_any()),
        ],
    )
}

/// The native error `class(message, code=code)`.
pub(crate) fn input_error(
    py: Python<'_>,
    class: ErrorId,
    message: &str,
    code: Option<&str>,
) -> PyErr {
    let raised: PyResult<Bound<'_, PyAny>> = registry::error(py, class).and_then(|class| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        if let Some(code) = code {
            options.set_item("code", code)?;
        }
        class.call((message,), Some(&options))
    });
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}
