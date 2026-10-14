//! Shared `sqb scenario` preparation: project, namespace, adapters, compile and selection.

use std::path::PathBuf;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyInt, PyString, PyTuple};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::scenario_command::constants::SCENARIO_NAMESPACE_ENV;
use sqlbuild_core::scenario_command::errors::ScenarioCommandError;
use sqlbuild_core::scenario_command::main::capture_dialect_required_error::capture_dialect_required_error;
use sqlbuild_core::scenario_command::main::format_captured_at::format_captured_at;
use sqlbuild_core::scenario_command::main::render_namespace_header::render_namespace_header;
use sqlbuild_core::scenario_command::main::resolve_scenario_namespace::resolve_scenario_namespace;
use sqlbuild_core::scenario_command::main::resolve_snapshot_limits::resolve_snapshot_limits;
use sqlbuild_core::scenario_command::main::select_scenarios::select_scenarios;
use sqlbuild_core::scenario_command::main::sql_analysis_purpose::sql_analysis_purpose;
use sqlbuild_core::scenario_command::main::sql_analysis_required_error::sql_analysis_required_error;
use sqlbuild_core::scenario_command::models::{
    NamespaceCandidates, ScenarioFile, ScenarioNamespace, ScenarioSelection, SnapshotLimitConfig,
    SnapshotLimitInputs, SnapshotLimits, SqlAnalysisCommand,
};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};
use crate::bindings::_helpers::discovery::guidance::sql_analysis_guidance;

pub(crate) const NATIVE_MODULE: &str = "sqlbuild._native";
const ERRORS_MODULE: &str = "sqlbuild.cli.commands.exceptions";
const REJECT_UNIT_TESTS_MODULE: &str = "sqlbuild.compiler.pipeline.main.reject_unit_test_selectors";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const SCENARIO_CONFIG_MODULE: &str = "sqlbuild._native";
const ADAPTERS_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.adapters";
const EXTERNAL_REFS_MODULE: &str = "sqlbuild.cli.commands._helpers.planning.external_refs";
const PIPELINE_MODELS: &str = "sqlbuild.compiler.pipeline.models";
const LIFECYCLE_MODULE: &str = "sqlbuild.runtime.observability.classes.operation_lifecycle";
const COLOR_MODULE: &str = "sqlbuild.presentation.main.supports_color";
const SCENARIO_MODELS: &str = "sqlbuild.executor.scenario.models";
const METADATA_MODULE: &str = "importlib.metadata";
const DISTRIBUTION_NAME: &str = "sqlbuild";
const UNKNOWN_VERSION: &str = "unknown";

pub(crate) fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

pub(crate) fn optional_text<'py>(py: Python<'py>, value: Option<&str>) -> Bound<'py, PyAny> {
    value.map_or_else(|| py.None().into_bound(py), |value| text(py, value))
}

/// `CliUserError(message, code=..., help=...)`.
pub(crate) fn cli_user_error(py: Python<'_>, error: ScenarioCommandError) -> PyErr {
    let raised: PyResult<Bound<'_, PyAny>> = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", error.code)?;
        options.set_item("help", error.help)?;
        imported(py, ERRORS_MODULE, "CliUserError")?.call((error.message,), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// The progress stream: `write` then `flush`.
pub(crate) fn write(stream: &Bound<'_, PyAny>, value: &str) -> PyResult<()> {
    stream.call_method1("write", (value,))?;
    Ok(())
}

pub(crate) fn flush(stream: &Bound<'_, PyAny>) -> PyResult<()> {
    stream.call_method0("flush")?;
    Ok(())
}

/// `hasattr(stream, "isatty") and stream.isatty()`.
pub(crate) fn stream_isatty(stream: &Bound<'_, PyAny>) -> PyResult<bool> {
    if !stream.hasattr("isatty")? {
        return Ok(false);
    }
    stream.call_method0("isatty")?.is_truthy()
}

/// The project, its discovered inputs and the effective scenario namespace.
pub(crate) struct ScenarioProject<'py> {
    pub(crate) project_dir: Bound<'py, PyAny>,
    pub(crate) discovered: Bound<'py, PyAny>,
    pub(crate) namespace: ScenarioNamespace,
    pub(crate) selectors: Bound<'py, PyAny>,
    pub(crate) exclude: Bound<'py, PyAny>,
}

fn config_namespace(config: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    config
        .getattr("scenario")?
        .getattr("run_namespace")?
        .extract()
}

/// `dataclasses.replace(value, **{name: replacement})`.
fn replaced<'py>(
    value: &Bound<'py, PyAny>,
    (name, replacement): (&str, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let changes: Bound<'py, PyDict> = PyDict::new(value.py());
    changes.set_item(name, replacement)?;
    value
        .py()
        .import("dataclasses")?
        .getattr("replace")?
        .call((value,), Some(&changes))
}

/// Discover the project, reject unit-test selectors and apply the effective namespace.
pub(crate) fn discover_project<'py>(
    py: Python<'py>,
    request: &Bound<'py, PyAny>,
) -> PyResult<ScenarioProject<'py>> {
    let project_dir: Bound<'py, PyAny> = match request.getattr("project_dir")? {
        directory if !directory.is_none() => directory,
        _ => py.import("pathlib")?.getattr("Path")?.call_method0("cwd")?,
    };
    let discovered: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[("project_dir", project_dir.clone())],
    )?;
    let selectors: Bound<'py, PyAny> = request.getattr("selectors")?;
    let exclude: Bound<'py, PyAny> = request.getattr("exclude")?;
    call_with(
        &imported(py, REJECT_UNIT_TESTS_MODULE, "reject_unit_test_selectors")?,
        &[
            ("select", selectors.clone()),
            ("exclude", exclude.clone()),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let local_config: Bound<'py, PyAny> = discovered.getattr("local_config")?;
    let candidates: NamespaceCandidates = NamespaceCandidates {
        cli: request.getattr("scenario_namespace")?.extract()?,
        env: py
            .import("os")?
            .getattr("environ")?
            .call_method1("get", (SCENARIO_NAMESPACE_ENV,))?
            .extract()?,
        local_config: config_namespace(&local_config)?,
        project_config: config_namespace(&discovered.getattr("project_config")?)?,
    };
    let namespace: ScenarioNamespace =
        resolve_scenario_namespace(candidates).map_err(|error| cli_user_error(py, error))?;
    let discovered: Bound<'py, PyAny> = match &namespace.value {
        Some(value) => {
            let scenario: Bound<'py, PyAny> = replaced(
                &local_config.getattr("scenario")?,
                ("run_namespace", text(py, value)),
            )?;
            replaced(
                &discovered,
                (
                    "local_config",
                    replaced(&local_config, ("scenario", scenario))?,
                ),
            )?
        }
        None => discovered,
    };
    Ok(ScenarioProject {
        project_dir,
        discovered,
        namespace,
        selectors,
        exclude,
    })
}

/// Raise when SQL analysis is off by flag or by a config file.
pub(crate) fn require_sql_analysis(
    project: &ScenarioProject<'_>,
    (command, disabled_by_flag): (SqlAnalysisCommand, bool),
) -> PyResult<()> {
    let py: Python<'_> = project.discovered.py();
    let guidance: Option<(String, String)> = if disabled_by_flag {
        None
    } else {
        sql_analysis_guidance(&project.discovered, sql_analysis_purpose(command))?
    };
    match sql_analysis_required_error(command, disabled_by_flag, guidance) {
        Some(error) => Err(cli_user_error(py, error)),
        None => Ok(()),
    }
}

/// The adapter named by the project's effective configuration.
pub(crate) fn project_adapter_name(project: &ScenarioProject<'_>) -> PyResult<String> {
    let py: Python<'_> = project.discovered.py();
    call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            (
                "project_config",
                project.discovered.getattr("project_config")?,
            ),
            ("local_config", project.discovered.getattr("local_config")?),
        ],
    )?
    .extract()
}

pub(crate) fn resolve_adapter<'py>(
    project: &ScenarioProject<'py>,
    adapter_name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.discovered.py();
    call_with(
        &imported(py, ADAPTERS_MODULE, "resolve_adapter")?,
        &[
            ("adapter_name", text(py, adapter_name)),
            ("project_dir", project.project_dir.clone()),
        ],
    )
}

/// The adapter's SQL analysis dialect, which snapshots require.
pub(crate) fn require_capture_dialect(
    adapter: &Bound<'_, PyAny>,
    adapter_name: &str,
) -> PyResult<String> {
    let dialect: Option<String> = adapter.call_method0("sql_analysis_dialect")?.extract()?;
    dialect
        .ok_or_else(|| cli_user_error(adapter.py(), capture_dialect_required_error(adapter_name)))
}

pub(crate) fn project_connection_config<'py>(
    project: &ScenarioProject<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.discovered.py();
    call_with(
        &imported(py, NATIVE_MODULE, "resolve_project_connection_config")?,
        &[
            ("discovered_inputs", project.discovered.clone()),
            ("project_dir", project.project_dir.clone()),
        ],
    )
}

/// `not no_color and supports_color()`.
pub(crate) fn style(request: &Bound<'_, PyAny>) -> PyResult<CliStyle> {
    let use_color: bool = !request.getattr("no_color")?.is_truthy()?
        && imported(request.py(), COLOR_MODULE, "supports_color")?
            .call0()?
            .is_truthy()?;
    Ok(CliStyle { use_color })
}

/// Write the namespace line, then the execution header with the selected target.
pub(crate) fn write_headers<'py>(
    stream: &Bound<'py, PyAny>,
    project: &ScenarioProject<'py>,
    (command, concurrency, style): (&str, i64, CliStyle),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = stream.py();
    write(stream, &render_namespace_header(&project.namespace))?;
    let selectors: Vec<String> = project.selectors.extract()?;
    let planning: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "PlanningProgressReporter")?,
        &[
            ("stream", stream.clone()),
            ("use_color", boolean(py, style.use_color)),
        ],
    )?;
    write(stream, "\n")?;
    let target: Option<String> = (!selectors.is_empty()).then(|| selectors.join(" "));
    call_with(
        &imported(py, NATIVE_MODULE, "write_execution_header")?,
        &[
            ("stream", stream.clone()),
            ("command", text(py, command)),
            ("target", optional_text(py, target.as_deref())),
            ("concurrency", int(py, concurrency)),
            ("use_color", boolean(py, style.use_color)),
        ],
    )?;
    Ok(planning)
}

/// The adapter, compile options and planning progress of one scenario compile.
pub(crate) struct CompileInputs<'a, 'py> {
    pub(crate) adapter: &'a Bound<'py, PyAny>,
    pub(crate) options: &'a [(&'a str, Bound<'py, PyAny>)],
    pub(crate) planning: &'a Bound<'py, PyAny>,
}

/// Compile the project inside the project compile lifecycle.
pub(crate) fn compile<'py>(
    project: &ScenarioProject<'py>,
    inputs: CompileInputs<'_, 'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let CompileInputs {
        adapter,
        options,
        planning,
    } = inputs;
    let py: Python<'py> = project.discovered.py();
    let resolver: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            EXTERNAL_REFS_MODULE,
            "resolve_external_sql_reference_resolver",
        )?,
        &[
            ("project_dir", project.project_dir.clone()),
            ("discovered_inputs", project.discovered.clone()),
        ],
    )?;
    let mut pairs: Vec<(&str, Bound<'py, PyAny>)> = options.to_vec();
    pairs.push(("external_sql_reference_resolver", resolver));
    let options: Bound<'py, PyAny> = call_with(
        &imported(py, PIPELINE_MODELS, "CompilePipelineOptions")?,
        &pairs,
    )?;
    let lifecycle: Bound<'py, PyAny> = call_with(
        &imported(py, LIFECYCLE_MODULE, "OperationLifecycle")?,
        &[
            ("operation_kind", text(py, "project")),
            ("operation_name", text(py, "project_compile")),
        ],
    )?;
    within(&lifecycle, |_| {
        call_with(
            &imported(py, NATIVE_MODULE, "run_compile_only_pipeline")?,
            &[
                ("discovered_inputs", project.discovered.clone()),
                ("adapter", adapter.clone()),
                ("options", options.clone()),
                ("on_progress", planning.getattr("on_progress")?),
            ],
        )
    })
}

/// The compiled scenarios the selectors and exclusions select, in selection order.
pub(crate) fn selected_scenarios<'py>(
    pipeline: &Bound<'py, PyAny>,
    (selectors, exclude, project_dir): (&[String], &[String], &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = pipeline.py();
    let compiled: Vec<Bound<'py, PyAny>> = pipeline
        .getattr("project")?
        .getattr("sql_scenarios")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let mut files: Vec<ScenarioFile> = Vec::with_capacity(compiled.len());
    for scenario in &compiled {
        let file: Bound<'py, PyAny> = scenario.getattr("scenario_file")?;
        files.push(ScenarioFile {
            name: scenario.getattr("name")?.extract()?,
            file_path: file.getattr("file_path")?.extract()?,
            relative_path: file.getattr("relative_path")?.extract()?,
        });
    }
    let project_dir: PathBuf = project_dir.extract()?;
    let indices: Vec<usize> = select_scenarios(
        &files,
        ScenarioSelection {
            selectors,
            exclude,
            project_dir: &project_dir,
        },
    )
    .map_err(|error| cli_user_error(py, error))?;
    PyTuple::new(py, indices.into_iter().map(|index| compiled[index].clone()))
}

fn optional_int(value: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<i64>> {
    value.getattr(name)?.extract()
}

/// The snapshot capture limits from the request, the scenario config and the defaults.
pub(crate) fn capture_limits<'py>(
    request: &Bound<'py, PyAny>,
    project: &ScenarioProject<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let inputs: Bound<'py, PyAny> = request.getattr("limit_inputs")?;
    let configured: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            SCENARIO_CONFIG_MODULE,
            "resolve_effective_scenario_config",
        )?,
        &[
            (
                "project_config",
                project.discovered.getattr("project_config")?,
            ),
            ("local_config", project.discovered.getattr("local_config")?),
        ],
    )?
    .getattr("snapshot_limits")?;
    let limits: SnapshotLimits = resolve_snapshot_limits(
        SnapshotLimitInputs {
            max_rows_per_relation: optional_int(&inputs, "max_snapshot_rows")?,
            max_total_rows: optional_int(&inputs, "max_snapshot_total_rows")?,
            max_bytes_per_relation: optional_int(&inputs, "max_snapshot_bytes")?,
            max_total_bytes: optional_int(&inputs, "max_snapshot_total_bytes")?,
            force: inputs.getattr("force")?.is_truthy()?,
        },
        SnapshotLimitConfig {
            max_rows_per_relation: optional_int(&configured, "max_rows_per_relation")?,
            max_total_rows: optional_int(&configured, "max_total_rows")?,
            max_bytes_per_relation: optional_int(&configured, "max_bytes_per_relation")?,
            max_total_bytes: optional_int(&configured, "max_total_bytes")?,
        },
    );
    call_with(
        &imported(py, SCENARIO_MODELS, "ScenarioSnapshotCaptureLimits")?,
        &[
            (
                "max_rows_per_relation",
                int(py, limits.max_rows_per_relation),
            ),
            ("max_total_rows", int(py, limits.max_total_rows)),
            (
                "max_bytes_per_relation",
                int(py, limits.max_bytes_per_relation),
            ),
            ("max_total_bytes", int(py, limits.max_total_bytes)),
            ("force", boolean(py, limits.force)),
        ],
    )
}

fn sqlbuild_version(py: Python<'_>) -> PyResult<String> {
    let metadata: Bound<'_, PyAny> = py.import(METADATA_MODULE)?.into_any();
    match metadata.getattr("version")?.call1((DISTRIBUTION_NAME,)) {
        Ok(version) => version.extract(),
        Err(error) if error.is_instance(py, &metadata.getattr("PackageNotFoundError")?) => {
            Ok(UNKNOWN_VERSION.to_owned())
        }
        Err(error) => Err(error),
    }
}

/// Capture settings with the current capture time and SQLBuild version.
pub(crate) fn capture_settings<'py>(
    py: Python<'py>,
    (capture_adapter, capture_dialect, retain): (&str, &str, bool),
    limits: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let epoch_seconds: i64 = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |elapsed| {
            i64::try_from(elapsed.as_secs()).unwrap_or(i64::MAX)
        });
    call_with(
        &imported(py, SCENARIO_MODELS, "ScenarioCaptureSettings")?,
        &[
            ("captured_at", text(py, &format_captured_at(epoch_seconds))),
            ("capture_adapter", text(py, capture_adapter)),
            ("capture_dialect", text(py, capture_dialect)),
            ("sqlbuild_version", text(py, &sqlbuild_version(py)?)),
            ("retain", boolean(py, retain)),
            ("limits", limits),
        ],
    )
}

pub(crate) fn int(py: Python<'_>, value: i64) -> Bound<'_, PyAny> {
    PyInt::new(py, value).into_any()
}

pub(crate) fn boolean(py: Python<'_>, value: bool) -> Bound<'_, PyAny> {
    PyBool::new(py, value).to_owned().into_any()
}
