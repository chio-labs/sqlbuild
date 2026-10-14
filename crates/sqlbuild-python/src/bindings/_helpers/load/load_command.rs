//! `sqb load`: run the selected source loaders and report each load.

use std::time::Instant;

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyInt, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::load_command::main::load_counts::load_counts;
use sqlbuild_core::load_command::main::load_exit_code::load_exit_code;
use sqlbuild_core::load_command::main::render_empty_load::render_empty_load;
use sqlbuild_core::load_command::main::render_load_footer::render_load_footer;
use sqlbuild_core::load_command::main::render_load_plan::render_load_plan;
use sqlbuild_core::load_command::main::render_load_ready::render_load_ready;
use sqlbuild_core::load_command::models::{LoadCounts, LoadResultText};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::load::load_progress::{
    LoadCallbackRelay, LoadProgressReporter, load_result_text,
};
use crate::bindings::_helpers::load::load_selection::{
    LoadProject, LoaderDefaults, loader_defaults,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const ERRORS_MODULE: &str = "sqlbuild.cli.commands.exceptions";
const COLOR_MODULE: &str = "sqlbuild.presentation.main.supports_color";
const REJECT_UNIT_TESTS_MODULE: &str =
    "sqlbuild.compiler.pipeline.main._reject_unit_test_selectors";
const EFFECTIVE_TARGET_MODULE: &str = "sqlbuild._native";
const EFFECTIVE_RUNTIME_MODULE: &str = "sqlbuild._native";
const EFFECTIVE_SETTINGS_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const ADAPTERS_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.adapters";
const RELATION_LOOKUP_MODULE: &str = "sqlbuild.adapter.relations.main.relation_lookup";
const CURSOR_OVERRIDES_MODULE: &str =
    "sqlbuild.compiler.planner.main.cursor_window._typed_cursor_overrides";
const PLANNER_MODELS: &str = "sqlbuild.compiler.planner.models";
const PROVIDER_SESSION_MODULE: &str = "sqlbuild.provider.main.session";
const PYTHON_NODE_MODELS: &str = "sqlbuild.python_nodes.models";
const PYTHON_NODE_TYPES: &str = "sqlbuild.python_nodes.types";
const CURSOR_PARSING_MODULE: &str = "sqlbuild.cli.commands._helpers.input.parsing";
const LOAD_MODELS: &str = "sqlbuild.executor.load.models";
const LOAD_RUN_MODULE: &str = "sqlbuild.executor.load.main.run";
const LOADER_NODE_KEY: &str = "sqlbuild_loader_node";
const EXECUTION_COMMAND: &str = "sqb load";

/// The discovered project, selected loads and output context of one load.
struct Invocation<'py> {
    project_dir: Bound<'py, PyAny>,
    discovered: Bound<'py, PyAny>,
    selected: Vec<Bound<'py, PyAny>>,
    references: Vec<Bound<'py, PyAny>>,
    relation_sources: Vec<Bound<'py, PyAny>>,
    style: CliStyle,
    stream: Bound<'py, PyAny>,
}

/// The adapter, connection, runtime and providers prepared for execution.
struct Preparation<'py> {
    adapter_name: String,
    adapter: Bound<'py, PyAny>,
    connection_config: Bound<'py, PyAny>,
    runtime: (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>),
    concurrency: i64,
    cursor_overrides: Bound<'py, PyAny>,
    provider_session: Bound<'py, PyAny>,
    project_relations: Bound<'py, PyAny>,
}

fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

fn write(stream: &Bound<'_, PyAny>, value: &str) -> PyResult<()> {
    stream.call_method1("write", (value,))?;
    stream.call_method0("flush")?;
    Ok(())
}

fn invocation<'py>(py: Python<'py>, request: &Bound<'py, PyAny>) -> PyResult<Invocation<'py>> {
    let project_dir: Bound<'py, PyAny> = match request.getattr("project_dir")? {
        directory if !directory.is_none() => directory,
        _ => py.import("pathlib")?.getattr("Path")?.call_method0("cwd")?,
    };
    let discovered: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "discover_project_inputs")?,
        &[("project_dir", project_dir.clone())],
    )?;
    let select: Bound<'py, PyAny> = request.getattr("select")?;
    let exclude: Bound<'py, PyAny> = request.getattr("exclude")?;
    call_with(
        &imported(py, REJECT_UNIT_TESTS_MODULE, "reject_unit_test_selectors")?,
        &[
            ("select", select.clone()),
            ("exclude", exclude.clone()),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let selected_target: Bound<'py, PyAny> = request.getattr("selected_target")?;
    let target_config: Bound<'py, PyAny> = call_with(
        &imported(py, EFFECTIVE_TARGET_MODULE, "build_effective_target_config")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("selected_target", selected_target.clone()),
        ],
    )?;
    let defaults: LoaderDefaults<'py> = loader_defaults(
        &discovered,
        (
            &selected_target,
            &target_config,
            &request.getattr("cli_vars")?,
        ),
    )?;
    let project: LoadProject<'py> = LoadProject::new(&discovered, &target_config)?;
    let selected: Vec<Bound<'py, PyAny>> = project.selected_entries(
        (
            &select.extract::<Vec<String>>()?,
            &exclude.extract::<Vec<String>>()?,
        ),
        &defaults,
    )?;
    let references: Vec<Bound<'py, PyAny>> = project.reference_entries(&selected, &defaults)?;
    let machine_output: bool = request.getattr("json_output")?.extract()?;
    let use_color: bool = !request.getattr("no_color")?.extract::<bool>()?
        && !machine_output
        && imported(py, COLOR_MODULE, "supports_color")?
            .call0()?
            .extract::<bool>()?;
    let stream: Bound<'py, PyAny> =
        py.import("sys")?
            .getattr(if machine_output { "stderr" } else { "stdout" })?;
    Ok(Invocation {
        project_dir,
        discovered,
        selected,
        references,
        relation_sources: project.sources,
        style: CliStyle { use_color },
        stream,
    })
}

fn user_error(py: Python<'_>, message: String) -> PyErr {
    match imported(py, ERRORS_MODULE, "CliUserError").and_then(|class| class.call1((message,))) {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

fn target_name<'py>(source: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let table: Bound<'_, PyAny> = source.getattr("table")?;
    if table.is_truthy()? {
        Ok(table)
    } else {
        source.getattr("name")
    }
}

/// Refuse a load whose skipped intermediate loaders have no target relation yet.
fn check_reference_targets(
    invocation: &Invocation<'_>,
    (adapter, connection_config): (&Bound<'_, PyAny>, &Bound<'_, PyAny>),
) -> PyResult<()> {
    if invocation.references.is_empty() {
        return Ok(());
    }
    let py: Python<'_> = adapter.py();
    let selected_names: Vec<String> = invocation
        .selected
        .iter()
        .map(|source| source.getattr("name")?.extract())
        .collect::<PyResult<_>>()?;
    let connection: Bound<'_, PyAny> = adapter.call_method1("connect", (connection_config,))?;
    let checked: PyResult<()> = (|| {
        let locations: Vec<Bound<'_, PyTuple>> = invocation
            .references
            .iter()
            .map(|source| {
                PyTuple::new(
                    py,
                    [
                        source.getattr("database")?,
                        source.getattr("schema")?,
                        target_name(source)?,
                    ],
                )
            })
            .collect::<PyResult<_>>()?;
        let lookup: Bound<'_, PyAny> = call_with(
            &imported(py, RELATION_LOOKUP_MODULE, "build_relation_lookup")?,
            &[
                ("adapter", adapter.clone()),
                ("connection", connection.clone()),
                ("locations", PyTuple::new(py, locations)?.into_any()),
            ],
        )?;
        for source in &invocation.references {
            let target: Bound<'_, PyAny> = target_name(source)?;
            let exists: bool = call_with(
                &lookup.getattr("exists")?,
                &[
                    ("database", source.getattr("database")?),
                    ("schema", source.getattr("schema")?),
                    ("name", target.clone()),
                ],
            )?
            .is_truthy()?;
            if !exists {
                return Err(user_error(
                    py,
                    format!(
                        "Selected source load requires intermediate loader '{}', but its target \
                         relation '{}' does not exist; use +{} to refresh upstream ingress \
                         dependencies",
                        source.getattr("name")?.str()?,
                        target.str()?,
                        selected_names.join(", ")
                    ),
                ));
            }
        }
        Ok(())
    })();
    let closed: PyResult<Bound<'_, PyAny>> = adapter.call_method1("close", (&connection,));
    checked?;
    closed?;
    Ok(())
}

/// Source relations loaders must not hard-code, or `None` when enforcement is off.
fn project_relations<'py>(
    invocation: &Invocation<'py>,
    adapter: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = adapter.py();
    if !invocation
        .discovered
        .getattr("project_config")?
        .getattr("references")?
        .getattr("enforce_explicit")?
        .is_truthy()?
    {
        return Ok(py.None().into_bound(py));
    }
    let sources: Bound<'py, PyDict> = PyDict::new(py);
    for source in invocation
        .relation_sources
        .iter()
        .chain(&invocation.references)
        .chain(&invocation.selected)
    {
        if source.getattr("expression")?.is_none() {
            sources.set_item(source.getattr("name")?, source)?;
        }
    }
    let reference_class: Bound<'py, PyAny> = imported(py, PYTHON_NODE_MODELS, "SqlResourceRef")?;
    let source_kind: Bound<'py, PyAny> =
        imported(py, PYTHON_NODE_TYPES, "SqlResourceRefKind")?.getattr("SOURCE")?;
    let render: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "render_source_relation")?;
    let relations: Bound<'py, PyDict> = PyDict::new(py);
    for (name, source) in sources.iter() {
        let key: Bound<'py, PyAny> = call_with(
            &reference_class,
            &[("kind", source_kind.clone()), ("name", name)],
        )?;
        let relation: Bound<'py, PyAny> =
            call_with(&render, &[("entry", source), ("adapter", adapter.clone())])?;
        relations.set_item(key, relation)?;
    }
    Ok(relations.into_any())
}

fn prepare<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Invocation<'py>,
) -> PyResult<Preparation<'py>> {
    let py: Python<'py> = request.py();
    let discovered: &Bound<'py, PyAny> = &invocation.discovered;
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let adapter: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTERS_MODULE, "resolve_adapter")?,
        &[
            ("adapter_name", adapter_name.clone()),
            ("project_dir", invocation.project_dir.clone()),
        ],
    )?;
    let connection_config: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_project_connection_config")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("project_dir", invocation.project_dir.clone()),
            ("selected_target", request.getattr("selected_target")?),
            ("cli_vars", request.getattr("cli_vars")?),
        ],
    )?;
    check_reference_targets(invocation, (&adapter, &connection_config))?;
    let runtime: (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>) = call_with(
        &imported(
            py,
            EFFECTIVE_RUNTIME_MODULE,
            "build_effective_runtime_config",
        )?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("selected_target", request.getattr("selected_target")?),
            ("cli_vars", request.getattr("cli_vars")?),
        ],
    )?
    .extract()?;
    let requested: Bound<'py, PyAny> = request.getattr("concurrency")?;
    let concurrency: i64 = if requested.is_none() {
        call_with(
            &imported(
                py,
                EFFECTIVE_SETTINGS_MODULE,
                "build_effective_settings_config",
            )?,
            &[("discovered_inputs", discovered.clone())],
        )?
        .getattr("concurrency")?
        .extract()?
    } else {
        requested.extract()?
    };
    let typed: Bound<'py, PyAny> = call_with(
        &imported(py, CURSOR_OVERRIDES_MODULE, "typed_cursor_overrides")?,
        &[("cursor_overrides", request.getattr("cursor_overrides")?)],
    )?;
    let cursor_overrides: Bound<'py, PyAny> = if typed.is_truthy()? {
        typed
    } else {
        imported(py, PLANNER_MODELS, "CursorOverrides")?.call0()?
    };
    let provider_session: Bound<'py, PyAny> = call_with(
        &imported(py, PROVIDER_SESSION_MODULE, "build_provider_session")?,
        &[("discovered_providers", discovered.getattr("providers")?)],
    )?;
    Ok(Preparation {
        adapter_name: adapter_name.extract()?,
        project_relations: project_relations(invocation, &adapter)?,
        adapter,
        connection_config,
        runtime,
        concurrency: concurrency.max(1),
        cursor_overrides,
        provider_session,
    })
}

fn cursor<'py>(
    overrides: &Bound<'py, PyAny>,
    (field, parser): (&str, &str),
) -> PyResult<Bound<'py, PyAny>> {
    imported(overrides.py(), CURSOR_PARSING_MODULE, parser)?.call1((overrides.getattr(field)?,))
}

/// The executor's runtime parameters for this load.
fn runtime_params<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Invocation<'py>,
    preparation: &Preparation<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let (target_name, effective_vars, run_id) = &preparation.runtime;
    let overrides: &Bound<'py, PyAny> = &preparation.cursor_overrides;
    call_with(
        &imported(py, LOAD_MODELS, "LoadRuntimeParams")?,
        &[
            ("run_id", run_id.clone()),
            (
                "runtime_dir",
                invocation
                    .project_dir
                    .call_method1("__truediv__", ("target",))?,
            ),
            ("target", target_name.clone()),
            ("vars", effective_vars.clone()),
            ("is_reload", request.getattr("reload")?),
            (
                "start_cursor_ts",
                cursor(overrides, ("start_ts", "parse_cursor_timestamp"))?,
            ),
            (
                "end_cursor_ts",
                cursor(overrides, ("end_ts", "parse_cursor_timestamp"))?,
            ),
            (
                "start_cursor_int",
                cursor(overrides, ("start_int", "parse_cursor_integer"))?,
            ),
            (
                "end_cursor_int",
                cursor(overrides, ("end_int", "parse_cursor_integer"))?,
            ),
            (
                "use_color",
                PyBool::new(py, invocation.style.use_color)
                    .to_owned()
                    .into_any(),
            ),
            (
                "providers",
                preparation.provider_session.getattr("providers")?,
            ),
            ("project_relations", preparation.project_relations.clone()),
        ],
    )
}

/// Run the selected loads with progress callbacks; returns the results and elapsed seconds.
fn execute<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Invocation<'py>,
    preparation: &Preparation<'py>,
) -> PyResult<(Vec<Bound<'py, PyAny>>, f64)> {
    let py: Python<'py> = request.py();
    let started: Instant = Instant::now();
    let event_writer: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "ExecutionEventWriter")?.call0()?;
    let order: Bound<'py, PyDict> = PyDict::new(py);
    for (index, source) in invocation.selected.iter().enumerate() {
        order.set_item(source.getattr("name")?, index + 1)?;
    }
    let reporter: Bound<'py, LoadProgressReporter> =
        imported(py, NATIVE_MODULE, "LoadProgressReporter")?
            .call(
                (),
                Some(&{
                    let options: Bound<'py, PyDict> = PyDict::new(py);
                    options.set_item("stream", &invocation.stream)?;
                    options.set_item("use_color", invocation.style.use_color)?;
                    options.set_item("source_order", order)?;
                    options.set_item("total_count", invocation.selected.len())?;
                    options
                }),
            )?
            .downcast_into()?;
    let connection: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
        &[
            ("adapter_name", text(py, &preparation.adapter_name)),
            ("stream", invocation.stream.clone()),
            (
                "blank_line_after_complete",
                PyBool::new(py, true).to_owned().into_any(),
            ),
            (
                "use_color",
                PyBool::new(py, invocation.style.use_color)
                    .to_owned()
                    .into_any(),
            ),
        ],
    )?;
    let relay: Bound<'py, LoadCallbackRelay> = Bound::new(
        py,
        LoadCallbackRelay {
            reporter: reporter.clone().unbind(),
            event_writer: event_writer.clone().unbind(),
            connection: connection.clone().unbind(),
        },
    )?;
    let executed: PyResult<Vec<Bound<'py, PyAny>>> = (|| {
        let callbacks: Bound<'py, PyAny> = call_with(
            &imported(py, LOAD_MODELS, "LoadCallbacks")?,
            &[
                ("on_load_start", reporter.getattr("on_start")?),
                ("on_load_progress", reporter.getattr("on_progress")?),
                ("on_load_complete", relay.getattr("on_load_complete")?),
                (
                    "on_connection_start",
                    connection.getattr("on_connection_start")?,
                ),
                (
                    "on_connection_complete",
                    relay.getattr("on_connection_complete")?,
                ),
                ("on_connection_error", relay.getattr("on_connection_error")?),
            ],
        )?;
        call_with(
            &imported(py, LOAD_RUN_MODULE, "run_load_pipeline")?,
            &[
                (
                    "sources",
                    PyTuple::new(py, &invocation.selected)?.into_any(),
                ),
                (
                    "reference_sources",
                    PyTuple::new(py, &invocation.references)?.into_any(),
                ),
                (
                    "loader_functions",
                    invocation.discovered.getattr("loader_functions")?,
                ),
                ("connection_config", preparation.connection_config.clone()),
                ("adapter", preparation.adapter.clone()),
                (
                    "max_concurrency",
                    PyInt::new(py, preparation.concurrency).into_any(),
                ),
                ("runtime", runtime_params(request, invocation, preparation)?),
                ("callbacks", callbacks),
            ],
        )?
        .try_iter()?
        .collect()
    })();
    let closed: PyResult<Bound<'py, PyAny>> = event_writer.call_method0("close");
    let results: Vec<Bound<'py, PyAny>> = executed?;
    closed?;
    Ok((results, started.elapsed().as_secs_f64()))
}

fn write_json(request: &Bound<'_, PyAny>, results: &[Bound<'_, PyAny>]) -> PyResult<()> {
    let py: Python<'_> = request.py();
    let payload: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "format_load_execution_json")?,
        &[("results", PyTuple::new(py, results)?.into_any())],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "write_execution_json_output")?,
        &[
            ("payload", payload),
            ("json_output", request.getattr("json_output")?),
            ("json_output_path", request.getattr("json_output_path")?),
        ],
    )?;
    Ok(())
}

fn loader_node_flag(source: &Bound<'_, PyAny>) -> PyResult<bool> {
    let py: Python<'_> = source.py();
    Ok(source
        .getattr("meta")?
        .call_method1("get", (LOADER_NODE_KEY,))?
        .is(PyBool::new(py, true).to_owned()))
}

/// Run one `sqb load` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_load_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let invocation: Invocation<'_> = invocation(py, request)?;
    write(
        &invocation.stream,
        &render_load_ready(invocation.selected.len(), invocation.style),
    )?;
    if invocation.selected.is_empty() {
        write(&invocation.stream, &render_empty_load(invocation.style))?;
        write_json(request, &[])?;
        return Ok(0);
    }
    let preparation: Preparation<'_> = prepare(request, &invocation)?;
    let outcome: PyResult<(Vec<Bound<'_, PyAny>>, f64)> = (|| {
        let entries: Vec<(String, bool)> = invocation
            .selected
            .iter()
            .map(|source| {
                Ok((
                    source.getattr("name")?.extract()?,
                    loader_node_flag(source)?,
                ))
            })
            .collect::<PyResult<_>>()?;
        write(
            &invocation.stream,
            &render_load_plan(&entries, invocation.style),
        )?;
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("stream", &invocation.stream)?;
        options.set_item("command", EXECUTION_COMMAND)?;
        options.set_item("target", py.None())?;
        options.set_item("concurrency", preparation.concurrency)?;
        options.set_item("use_color", invocation.style.use_color)?;
        imported(py, NATIVE_MODULE, "write_execution_header")?.call((), Some(&options))?;
        execute(request, &invocation, &preparation)
    })();
    let closed: PyResult<Bound<'_, PyAny>> = preparation.provider_session.call_method0("close");
    let (results, elapsed) = outcome?;
    closed?;
    let texts: Vec<LoadResultText> = results
        .iter()
        .map(load_result_text)
        .collect::<PyResult<_>>()?;
    let counts: LoadCounts = load_counts(&texts);
    write(
        &invocation.stream,
        &render_load_footer(&texts, (counts, elapsed), invocation.style),
    )?;
    write_json(request, &results)?;
    Ok(load_exit_code(counts))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_load_command, module)?)?;
    Ok(())
}
