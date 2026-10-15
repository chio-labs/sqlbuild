//! Resolve discovery, target, adapter, limits, connection and reporters for one build.

use std::time::Instant;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use sqlbuild_core::build_command::errors::BuildCommandError;
use sqlbuild_core::build_command::main::duration_limit_error::duration_limit_error;
use sqlbuild_core::build_command::models::DurationLimit;

use crate::bindings::_helpers::build_command::policies::build_command_error;
use crate::bindings::_helpers::build_command::support::{boolean, or_none, text};
use crate::bindings::_helpers::command_runtime::adapters::resolve_cli_adapter;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;

const NATIVE_MODULE: &str = "sqlbuild._native";
const SETTINGS_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const TARGET_CONFIG_MODULE: &str = "sqlbuild._native";
const TARGET_NAME_MODULE: &str = "sqlbuild._native";
const CONTRACT_MODELS: &str = "sqlbuild._native";
const DEFER_CONFLICT_CODE: &str = "C408";

/// One build's request, resolved invocation and output settings.
pub(crate) struct BuildContext<'py> {
    pub(crate) request: Bound<'py, PyAny>,
    pub(crate) invocation: Bound<'py, PyAny>,
    pub(crate) stream: Bound<'py, PyAny>,
    pub(crate) use_color: bool,
    pub(crate) verbose: bool,
    pub(crate) started: Instant,
    pub(crate) tracker: Bound<'py, PyAny>,
}

impl<'py> BuildContext<'py> {
    pub(crate) fn py(&self) -> Python<'py> {
        self.request.py()
    }

    pub(crate) fn request_flag(&self, name: &str) -> PyResult<bool> {
        self.request.getattr(name)?.is_truthy()
    }

    pub(crate) fn get(&self, name: &str) -> PyResult<Bound<'py, PyAny>> {
        self.invocation.getattr(name)
    }

    /// The requested concurrency, or the project setting.
    pub(crate) fn concurrency(&self, project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        or_none(self.request.getattr("concurrency")?, || {
            project.getattr("settings")?.getattr("concurrency")
        })
    }
}

fn target_config<'py>(
    discovered: &Bound<'py, PyAny>,
    target_name: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    call_with(
        &imported(py, TARGET_CONFIG_MODULE, "resolve_target_config")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
            ("target_name", target_name.clone()),
        ],
    )
}

fn execution_limits<'py>(
    discovered: &Bound<'py, PyAny>,
    target_name: &Bound<'py, PyAny>,
    (adapter_name, adapter): (&str, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let limits: Bound<'py, PyAny> = if target_name.is_none() {
        imported(py, CONTRACT_MODELS, "ExecutionLimitsConfig")?.call0()?
    } else {
        target_config(discovered, target_name)?.getattr("execution_limits")?
    };
    let limit: DurationLimit = DurationLimit {
        target_name: target_name.extract()?,
        adapter_name: adapter_name.to_owned(),
        configures_max_duration: !limits.getattr("max_duration")?.is_none(),
        max_duration_seconds: limits.getattr("max_duration_seconds")?.extract()?,
        adapter_limit_seconds: adapter
            .getattr("execution_duration_limit_seconds")?
            .extract()?,
        remediation: limits.getattr("remediation")?.extract()?,
    };
    if let Some(error) = duration_limit_error(&limit) {
        return Err(build_command_error(py, error));
    }
    Ok(limits)
}

/// Discover the project and resolve everything the build reads before compiling.
pub(crate) fn resolve_build_context<'py>(
    request: &Bound<'py, PyAny>,
    tracker: &Bound<'py, PyAny>,
    started: Instant,
) -> PyResult<BuildContext<'py>> {
    let py: Python<'py> = request.py();
    let project_dir: Bound<'py, PyAny> = or_none(request.getattr("project_dir")?, || {
        imported(py, "pathlib", "Path")?.call_method0("cwd")
    })?;
    let discovered: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[
            ("project_dir", project_dir.clone()),
            ("extract_output_column_locations", boolean(py, false)),
        ],
    )?;
    let selected_target: Bound<'py, PyAny> = request.getattr("selected_target")?;
    let target_name: Bound<'py, PyAny> = call_with(
        &imported(py, TARGET_NAME_MODULE, "resolve_target_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
            ("selected_target", selected_target.clone()),
        ],
    )?;
    let defer_clone_from: Bound<'py, PyAny> =
        or_none(request.getattr("defer_clone_from")?, || {
            if target_name.is_none() {
                return Ok(target_name.clone());
            }
            target_config(&discovered, &target_name)?.getattr("defer_clone_from")
        })?;
    if !request.getattr("defer_to")?.is_none() && !defer_clone_from.is_none() {
        return Err(build_command_error(
            py,
            BuildCommandError::new(
                Some(DEFER_CONFLICT_CODE),
                "--defer-clone-from cannot be used with --defer-to".to_owned(),
                None,
            ),
        ));
    }
    let adapter_name: String = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?
    .extract()?;
    let adapter: Bound<'py, PyAny> = resolve_cli_adapter(&text(py, &adapter_name), &project_dir)?;
    let limits: Bound<'py, PyAny> =
        execution_limits(&discovered, &target_name, (&adapter_name, &adapter))?;
    let connection_config: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_project_connection_config")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("project_dir", project_dir.clone()),
            ("selected_target", selected_target),
            ("cli_vars", request.getattr("cli_vars")?),
        ],
    )?;
    let machine_output: bool = request.getattr("json_output")?.is_truthy()?;
    let debug: bool = request.getattr("debug")?.is_truthy()?;
    let use_color: bool =
        !request.getattr("no_color")?.is_truthy()? && !machine_output && stdout_supports_color(py)?;
    let stream: Bound<'py, PyAny> = py.import("sys")?.getattr(if debug || machine_output {
        "stderr"
    } else {
        "stdout"
    })?;
    let connection_progress: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
        &[
            ("adapter_name", text(py, &adapter_name)),
            ("stream", stream.clone()),
            ("use_color", boolean(py, use_color)),
        ],
    )?;
    let planning_progress: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "PlanningProgressReporter")?,
        &[
            ("stream", stream.clone()),
            ("use_color", boolean(py, use_color)),
        ],
    )?;
    let load_sources: Bound<'py, PyAny> = request.getattr("load_sources")?;
    let should_load_sources: bool = request.getattr("reload_sources")?.is_truthy()?
        || if load_sources.is_none() {
            call_with(
                &imported(py, SETTINGS_MODULE, "build_effective_settings_config")?,
                &[("discovered_inputs", discovered.clone())],
            )?
            .getattr("auto_load_sources")?
            .is_truthy()?
        } else {
            load_sources.is_truthy()?
        };
    let invocation: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "BuildInvocation")?,
        &[
            ("effective_project_dir", project_dir),
            ("discovered_inputs", discovered),
            ("effective_defer_clone_from", defer_clone_from),
            ("adapter_name", text(py, &adapter_name)),
            ("adapter", adapter),
            ("connection_config", connection_config),
            ("use_color", boolean(py, use_color)),
            ("progress_stream", stream.clone()),
            ("connection_progress", connection_progress),
            ("planning_progress", planning_progress),
            ("should_load_sources", boolean(py, should_load_sources)),
            ("effective_target_name", target_name),
            ("execution_limits", limits),
        ],
    )?;
    Ok(BuildContext {
        request: request.clone(),
        invocation,
        stream,
        use_color,
        verbose: request.getattr("verbose")?.is_truthy()? || debug,
        started,
        tracker: tracker.clone(),
    })
}
