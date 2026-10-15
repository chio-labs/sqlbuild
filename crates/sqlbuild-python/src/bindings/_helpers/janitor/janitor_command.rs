//! `sqb janitor`: preview stale warehouse objects, confirm, and clean them up.

use pyo3::IntoPyObject;
use pyo3::exceptions::PyKeyboardInterrupt;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::janitor_planning::main::resolve_retention_days::resolve_retention_days;
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::janitor_text::errors::JanitorSettingsError;
use sqlbuild_core::janitor_text::main::janitor_completion_text::janitor_completion_text;
use sqlbuild_core::janitor_text::main::janitor_confirmation_phrase::janitor_confirmation_phrase;
use sqlbuild_core::janitor_text::main::janitor_confirmation_prompt::janitor_confirmation_prompt;
use sqlbuild_core::janitor_text::main::janitor_disabled_text::janitor_disabled_text;
use sqlbuild_core::janitor_text::main::janitor_plan_has_work::janitor_plan_has_work;
use sqlbuild_core::janitor_text::main::janitor_preview_complete_text::janitor_preview_complete_text;
use sqlbuild_core::janitor_text::main::janitor_preview_start_text::janitor_preview_start_text;
use sqlbuild_core::janitor_text::main::render_janitor_plan::render_janitor_plan;
use sqlbuild_core::janitor_text::main::validate_janitor_settings::validate_janitor_settings;
use sqlbuild_core::janitor_text::models::JanitorPlanText;

use crate::bindings::_helpers::janitor::janitor_phases::{
    JanitorCompiled, build_janitor_execution_plan, close_janitor_warehouse,
    compile_janitor_project, connect_janitor_warehouse, execute_janitor_cleanup,
};
use crate::bindings::_helpers::janitor::janitor_plan::{janitor_plan_text, janitor_result_counts};
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;

const NATIVE_MODULE: &str = "sqlbuild._native";
const ERRORS_MODULE: &str = "sqlbuild._native";
const PREVIEW_TARGET_MODULE: &str = "sqlbuild._native";
const TARGET_NAME_MODULE: &str = "sqlbuild._native";
const COMMAND_NAME: &str = "janitor";

fn imported<'py>(py: Python<'py>, module: &str, name: &str) -> PyResult<Bound<'py, PyAny>> {
    py.import(module)?.getattr(name)
}

fn keywords<'py>(
    py: Python<'py>,
    items: &[(&str, &Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyDict>> {
    let dict: Bound<'py, PyDict> = PyDict::new(py);
    for (name, value) in items {
        dict.set_item(*name, value)?;
    }
    Ok(dict)
}

fn settings_error(py: Python<'_>, error: JanitorSettingsError) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", error.code)?;
        imported(py, ERRORS_MODULE, "CliUserError")?.call((error.message,), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

fn write(py: Python<'_>, text: &str) -> PyResult<()> {
    py.import("sys")?
        .getattr("stdout")?
        .call_method1("write", (text,))?;
    Ok(())
}

fn flush(py: Python<'_>) -> PyResult<()> {
    py.import("sys")?.getattr("stdout")?.call_method0("flush")?;
    Ok(())
}

/// Discover the project and resolve the target and output context.
fn invocation<'py>(py: Python<'py>, request: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let project_dir: Bound<'py, PyAny> = match request.getattr("project_dir")? {
        directory if !directory.is_none() => directory,
        _ => py.import("pathlib")?.getattr("Path")?.call_method0("cwd")?,
    };
    let discovered: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "discover_project_inputs")?
        .call((), Some(&keywords(py, &[("project_dir", &project_dir)])?))?;
    let as_target: Bound<'py, PyAny> = request.getattr("as_target")?;
    let preview: Bound<'py, PyDict> = keywords(
        py,
        &[
            ("discovered_inputs", &discovered),
            ("as_target", &as_target),
        ],
    )?;
    preview.set_item("command_name", COMMAND_NAME)?;
    imported(py, PREVIEW_TARGET_MODULE, "validate_preview_target")?.call((), Some(&preview))?;
    let selected_target: Bound<'py, PyAny> = request.getattr("selected_target")?;
    let active_target: Bound<'py, PyAny> = imported(py, TARGET_NAME_MODULE, "resolve_target_name")?
        .call(
            (),
            Some(&keywords(
                py,
                &[
                    ("project_config", &discovered.getattr("project_config")?),
                    ("local_config", &discovered.getattr("local_config")?),
                    ("selected_target", &selected_target),
                ],
            )?),
        )?;
    let use_color: bool =
        !request.getattr("no_color")?.extract::<bool>()? && stdout_supports_color(py)?;
    let options: Bound<'py, PyDict> = keywords(
        py,
        &[
            ("effective_project_dir", &project_dir),
            ("discovered_inputs", &discovered),
            ("selected_target", &selected_target),
            ("active_target_name", &active_target),
            ("as_target", &as_target),
        ],
    )?;
    options.set_item("use_color", use_color)?;
    imported(py, NATIVE_MODULE, "JanitorInvocation")?.call((), Some(&options))
}

/// Effective retention settings, validated.
fn settings<'py>(
    py: Python<'py>,
    request: &Bound<'py, PyAny>,
    janitor: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let retention_days: Bound<'py, PyAny> = resolve_retention_days(
        request.getattr("retention_days")?.extract()?,
        janitor.getattr("retention_days")?.extract()?,
    )
    .into_pyobject(py)?
    .into_any();
    validate_janitor_settings(retention_days.extract()?, 0)
        .map_err(|error| settings_error(py, error))?;
    let requested: Bound<'py, PyAny> = request.getattr("direct_state_history_versions")?;
    let history: Bound<'py, PyAny> = if requested.is_none() {
        janitor.getattr("direct_state_history_versions")?
    } else {
        requested
    };
    validate_janitor_settings(0, history.extract()?).map_err(|error| settings_error(py, error))?;
    let options: Bound<'py, PyDict> = keywords(
        py,
        &[
            ("retention_days", &retention_days),
            ("direct_state_history_versions", &history),
            (
                "archive_retention_days",
                &janitor.getattr("archive_retention_days")?,
            ),
            (
                "drop_old_name_views",
                &request.getattr("drop_old_name_views")?,
            ),
        ],
    )?;
    imported(py, NATIVE_MODULE, "JanitorSettings")?.call((), Some(&options))
}

/// Ask for the exact confirmation phrase; an interrupt cancels.
fn confirmed(py: Python<'_>, plan: &JanitorPlanText) -> PyResult<bool> {
    write(py, &janitor_confirmation_prompt(plan))?;
    flush(py)?;
    match imported(py, "builtins", "input")?.call0() {
        Ok(response) => Ok(response.extract::<String>()? == janitor_confirmation_phrase(plan)),
        Err(error) if error.is_instance_of::<PyKeyboardInterrupt>(py) => {
            write(py, "\n")?;
            Ok(false)
        }
        Err(error) => Err(error),
    }
}

/// Plan, preview, confirm and clean up with an open warehouse connection.
fn clean(
    py: Python<'_>,
    request: &Bound<'_, PyAny>,
    (invocation, settings): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
    (compiled, connection): (&JanitorCompiled<'_>, &Bound<'_, PyAny>),
) -> PyResult<i32> {
    let style: CliStyle = CliStyle {
        use_color: invocation.getattr("use_color")?.extract()?,
    };
    let planning: Bound<'_, PyAny> =
        build_janitor_execution_plan((invocation, settings), compiled, connection)?;
    let plan: JanitorPlanText = janitor_plan_text(&planning)?;
    write(py, &render_janitor_plan(&plan, style))?;
    let blocked: i32 = i32::from(!plan.blocked_schemas.is_empty());
    let as_target: Option<String> = invocation.getattr("as_target")?.extract()?;
    if let Some(as_target) = as_target {
        let active: Option<String> = invocation.getattr("active_target_name")?.extract()?;
        write(
            py,
            &janitor_preview_complete_text(&as_target, active.as_deref(), style),
        )?;
        return Ok(blocked);
    }
    if blocked != 0 {
        return Ok(1);
    }
    if !janitor_plan_has_work(&plan) {
        return Ok(0);
    }
    if !request.getattr("auto_approve")?.extract::<bool>()? && !confirmed(py, &plan)? {
        write(py, "Janitor cancelled.\n")?;
        return Ok(1);
    }
    let result: Bound<'_, PyAny> = execute_janitor_cleanup(compiled, connection, &planning)?;
    write(
        py,
        &janitor_completion_text(&janitor_result_counts(&result)?, style),
    )?;
    Ok(0)
}

/// Run one `sqb janitor` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_janitor_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let invocation: Bound<'_, PyAny> = invocation(py, request)?;
    let style: CliStyle = CliStyle {
        use_color: invocation.getattr("use_color")?.extract()?,
    };
    let janitor: Bound<'_, PyAny> = invocation
        .getattr("discovered_inputs")?
        .getattr("project_config")?
        .getattr("janitor")?;
    if !janitor.getattr("enabled")?.is_truthy()? {
        write(py, &janitor_disabled_text(style))?;
        return Ok(0);
    }
    let settings: Bound<'_, PyAny> = settings(py, request, &janitor)?;
    let as_target: Option<String> = invocation.getattr("as_target")?.extract()?;
    if let Some(as_target) = &as_target {
        let active: Option<String> = invocation.getattr("active_target_name")?.extract()?;
        write(
            py,
            &janitor_preview_start_text(as_target, active.as_deref()),
        )?;
        flush(py)?;
    }
    let compiled: JanitorCompiled<'_> = compile_janitor_project(&invocation)?;
    let connection: Bound<'_, PyAny> = connect_janitor_warehouse(&invocation, &compiled)?;
    let outcome: PyResult<i32> = clean(
        py,
        request,
        (&invocation, &settings),
        (&compiled, &connection),
    );
    let closed: PyResult<()> = close_janitor_warehouse(&compiled, &connection);
    let code: i32 = outcome?;
    closed?;
    Ok(code)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_janitor_command, module)?)?;
    Ok(())
}
