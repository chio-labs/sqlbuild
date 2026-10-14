//! Best-effort delayed cost refresh of one pending or partial persisted run.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cost_command::constants::{
    HISTORY_SELECTOR, LATEST_SELECTOR, REFRESHABLE_STATUSES,
};
use sqlbuild_core::cost_command::main::accepts_cost_refresh::accepts_cost_refresh;
use sqlbuild_core::cost_command::models::CostCoverage;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const NATIVE_MODULE: &str = "sqlbuild._native";
const EFFECTIVE_TARGET_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const RESOLVE_ADAPTER_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.adapters";
const COST_TYPES: &str = "sqlbuild.cost.types";

fn coverage(summary: &Bound<'_, PyAny>) -> PyResult<CostCoverage> {
    Ok(CostCoverage {
        status: summary.getattr("status")?.getattr("value")?.extract()?,
        expected_statement_count: summary.getattr("expected_statement_count")?.extract()?,
        observed_statement_count: summary.getattr("observed_statement_count")?.extract()?,
        query_count: summary.getattr("query_count")?.extract()?,
        limitations: summary
            .getattr("limitations")?
            .try_iter()?
            .map(|limitation| limitation?.extract())
            .collect::<PyResult<_>>()?,
    })
}

/// The persisted record the selector names: latest, an exact run id, or a unique prefix.
fn refresh_record<'py>(
    project_dir: &Bound<'py, PyAny>,
    selector: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let resolve = || {
        call_with(
            &imported(py, NATIVE_MODULE, "resolve_cost_run")?,
            &[
                ("project_dir", project_dir.clone()),
                ("selector", selector.clone()),
            ],
        )
    };
    if selector.extract::<String>()? == LATEST_SELECTOR {
        return resolve();
    }
    let exact: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "read_cost_run")?,
        &[
            ("project_dir", project_dir.clone()),
            ("run_id", selector.clone()),
        ],
    )?;
    if !exact.is_none() {
        return Ok(exact);
    }
    resolve()
}

/// The target database the collection queries: the target's, else the connection's.
fn target_database<'py>(
    target_config: &Bound<'py, PyAny>,
    connection_config: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = target_config.py();
    if !target_config.is_none() {
        let database: Bound<'py, PyAny> = target_config.getattr("database")?;
        if !database.is_none() {
            return Ok(database);
        }
    }
    let database: Bound<'py, PyAny> = connection_config.call_method1("get", ("database",))?;
    if database.is_none() {
        return Ok(py.None().into_bound(py));
    }
    Ok(database.str()?.into_any())
}

fn refresh(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<()> {
    let selector: Bound<'_, PyAny> = request.getattr("selector")?;
    if selector.extract::<String>()? == HISTORY_SELECTOR {
        return Ok(());
    }
    let requested: Bound<'_, PyAny> = request.getattr("project_dir")?;
    let project_dir: Bound<'_, PyAny> = if requested.is_none() {
        imported(py, "pathlib", "Path")?.call_method0("cwd")?
    } else {
        requested
    };
    let record: Bound<'_, PyAny> = refresh_record(&project_dir, &selector)?;
    if record.is_none() {
        return Ok(());
    }
    let current: Bound<'_, PyAny> = record.getattr("cost")?;
    let status: String = current.getattr("status")?.getattr("value")?.extract()?;
    if !REFRESHABLE_STATUSES.contains(&status.as_str()) {
        return Ok(());
    }
    let target_name: Bound<'_, PyAny> = record.getattr("target_name")?;
    let discovered: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[("project_dir", project_dir.clone())],
    )?;
    let target_config: Bound<'_, PyAny> = call_with(
        &imported(py, EFFECTIVE_TARGET_MODULE, "build_effective_target_config")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("selected_target", target_name.clone()),
        ],
    )?;
    let adapter_name: Bound<'_, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let adapter: Bound<'_, PyAny> = call_with(
        &imported(py, RESOLVE_ADAPTER_MODULE, "resolve_adapter")?,
        &[
            ("adapter_name", adapter_name),
            ("project_dir", project_dir.clone()),
        ],
    )?;
    if !adapter.is_instance(&imported(py, COST_TYPES, "CostAwareAdapter")?)? {
        return Ok(());
    }
    let none_capability: Bound<'_, PyAny> =
        imported(py, COST_TYPES, "CostCapability")?.getattr("NONE")?;
    if adapter
        .call_method0("cost_capability")?
        .eq(none_capability)?
    {
        return Ok(());
    }
    let connection_config: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_project_connection_config")?,
        &[
            ("discovered_inputs", discovered),
            ("project_dir", project_dir.clone()),
            ("selected_target", target_name),
        ],
    )?;
    let run_id: Bound<'_, PyAny> = record.getattr("run_id")?;
    let ledger: Bound<'_, PyAny> = project_dir
        .call_method1("__truediv__", ("target",))?
        .call_method1("__truediv__", ("executions",))?
        .call_method1("__truediv__", (&run_id,))?
        .call_method1("__truediv__", ("statements.jsonl",))?;
    let summary: Bound<'_, PyAny> = call_with(
        &adapter.getattr("collect_run_cost")?,
        &[
            ("connection_config", connection_config.clone()),
            (
                "target_database",
                target_database(&target_config, &connection_config)?,
            ),
            ("run_id", run_id),
            ("started_at", record.getattr("started_at")?),
            ("completed_at", record.getattr("completed_at")?),
            ("statement_ledger_path", ledger),
            ("usd_per_credit", current.getattr("usd_per_credit")?),
            ("rate_source", current.getattr("rate_source")?),
        ],
    )?;
    if accepts_cost_refresh(&coverage(&current)?, &coverage(&summary)?) != Some(true) {
        return Ok(());
    }
    let changes: Bound<'_, PyDict> = PyDict::new(py);
    changes.set_item("cost", summary)?;
    let refreshed: Bound<'_, PyAny> =
        imported(py, "dataclasses", "replace")?.call((record,), Some(&changes))?;
    call_with(
        &imported(py, NATIVE_MODULE, "write_cost_run")?,
        &[("project_dir", project_dir), ("record", refreshed)],
    )?;
    Ok(())
}

/// Refresh one delayed record without making lookup depend on warehouse availability.
#[pyfunction]
pub(crate) fn refresh_pending_cost_run(py: Python<'_>, request: &Bound<'_, PyAny>) {
    let _ = refresh(py, request);
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(refresh_pending_cost_run, module)?)?;
    Ok(())
}
