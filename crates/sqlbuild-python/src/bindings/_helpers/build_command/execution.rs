//! Prepare build execution, run the build pipeline and the post-build Python checks.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_core::build_command::main::render_run_context::render_run_context;
use sqlbuild_core::build_command::models::{RunContextFacts, SelectorFileFact};
use sqlbuild_core::cli_text::models::CliStyle;

use crate::bindings::_helpers::build_command::invocation::BuildContext;
use crate::bindings::_helpers::build_command::lifecycle::{
    DirectPythonLifecycle, LifecycleInputs, prepare_direct_python_lifecycle,
};
use crate::bindings::_helpers::build_command::support::{
    boolean, display_text, emit, frozenset, joined, keyword_relay, line_writer, none, text, tuple,
};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, within};

const NATIVE_MODULE: &str = "sqlbuild._native";
const CALLBACKS_MODULE: &str = "sqlbuild.cli.commands.classes.build_progress_callbacks";
const PARSING_MODULE: &str = "sqlbuild.cli.commands._helpers.input.parsing";
const CURSOR_OVERRIDES_MODULE: &str =
    "sqlbuild.compiler.planner.main.cursor_window._typed_cursor_overrides";
const PLANNER_MODELS: &str = "sqlbuild.compiler.planner.models";
const BUILD_MODELS: &str = "sqlbuild.executor.build.models";
const PIPELINE_RUN_MODULE: &str = "sqlbuild.executor.pipeline.main.run";
const FRESHNESS_MODULE: &str = "sqlbuild.cli.commands._helpers.freshness.source_freshness";
const COST_CONTEXT_MODULE: &str = "sqlbuild.cost.classes.cost_context";
const CHECK_CORE_MODULE: &str = "sqlbuild.cli.commands._helpers.check.core";
const GRAPH_MODULE: &str = "sqlbuild.compiler.python_nodes.main._graph";
const CHECKS_MODULE: &str = "sqlbuild.executor.python_nodes.main._checks";
const EXECUTOR_PYTHON_MODELS: &str = "sqlbuild.executor.python_nodes.models";
const EXECUTION_COMMAND: &str = "sqb build";
const SUCCESS_STATUS: &str = "success";
const NODE_START: [&str; 2] = ["name", "resource_kind"];
const CONNECTION_TIMING: [&str; 2] = ["connection_count", "elapsed_seconds"];

/// Prepared callbacks, concurrency, cursors and Python lifecycle.
pub(crate) struct Preparation<'py> {
    pub(crate) callbacks: Bound<'py, PyAny>,
    pub(crate) concurrency: Bound<'py, PyAny>,
    connection_progress: Bound<'py, PyAny>,
    lifecycle: Bound<'py, DirectPythonLifecycle>,
    cursors: [Bound<'py, PyAny>; 4],
}

/// The build result and its finalized Python node results.
pub(crate) struct Outcome<'py> {
    pub(crate) result: Bound<'py, PyAny>,
    pub(crate) python_results: Bound<'py, PyAny>,
}

fn count(value: &Bound<'_, PyAny>, name: &str) -> PyResult<usize> {
    value.getattr(name)?.len()
}

fn validated_date(py: Python<'_>, value: Option<Bound<'_, PyAny>>) -> PyResult<Option<String>> {
    let Some(value) = value.filter(|value| value.is_instance_of::<pyo3::types::PyString>()) else {
        return Ok(None);
    };
    let datetime: Bound<'_, PyAny> = py.import("datetime")?.into_any();
    for kind in ["date", "datetime"] {
        match datetime
            .getattr(kind)?
            .call_method1("fromisoformat", (&value,))
        {
            Ok(_) => return Ok(Some(value.extract()?)),
            Err(error) if error.is_instance_of::<PyValueError>(py) => {}
            Err(error) => return Err(error),
        }
    }
    Ok(None)
}

fn run_context_facts(
    context: &BuildContext<'_>,
    pipeline: &Bound<'_, PyAny>,
    concurrency: &Bound<'_, PyAny>,
) -> PyResult<RunContextFacts> {
    let py: Python<'_> = context.py();
    let project: Bound<'_, PyAny> = pipeline.getattr("project")?;
    let plan: Bound<'_, PyAny> = pipeline.getattr("plan_output")?;
    let discovered: Bound<'_, PyAny> = context.get("discovered_inputs")?;
    let selected_count: usize = count(&plan, "model_entries")?
        + count(&plan, "seed_entries")?
        + count(&plan, "function_entries")?
        + count(&plan, "source_load_entries")?
        + count(pipeline, "python_plan_entries")?;
    let mut loaded_sources: usize = 0;
    for source in project.getattr("sources")?.try_iter()? {
        if !source?
            .getattr("source_entry")?
            .getattr("loader")?
            .is_none()
        {
            loaded_sources += 1;
        }
    }
    let total_count: usize = count(&project, "models")?
        + count(&project, "seeds")?
        + count(&project, "functions")?
        + loaded_sources
        + count(&discovered, "task_functions")?
        + count(&discovered, "asset_functions")?;
    let resolved: Bound<'_, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "describe_connection_warehouse")?,
        &[
            ("discovered_inputs", discovered),
            ("selected_target", project.getattr("effective_target_name")?),
            ("connection_config", context.get("connection_config")?),
        ],
    )?;
    let warehouse: Bound<'_, PyAny> = resolved.getattr("warehouse")?;
    let warehouse: Option<(String, String)> = if warehouse.is_none() {
        None
    } else {
        Some((
            display_text(&warehouse)?.unwrap_or_else(|| "not set".to_owned()),
            resolved.getattr("source")?.str()?.extract()?,
        ))
    };
    let variables: Bound<'_, PyAny> = project.getattr("effective_vars")?;
    let variable = |name: &str| -> PyResult<Option<Bound<'_, PyAny>>> {
        let value: Bound<'_, PyAny> = variables.call_method1("get", (name,))?;
        Ok((!value.is_none()).then_some(value))
    };
    let mut selector_files: Vec<SelectorFileFact> = Vec::new();
    for file in context.request.getattr("selector_files")?.try_iter()? {
        let file: Bound<'_, PyAny> = file?;
        selector_files.push(SelectorFileFact {
            path: file.getattr("path")?.str()?.extract()?,
            selector_count: file.getattr("selector_count")?.extract()?,
        });
    }
    Ok(RunContextFacts {
        command: EXECUTION_COMMAND.to_owned(),
        run_id: display_text(&project.getattr("run_id")?)?,
        target: display_text(&project.getattr("effective_target_name")?)?,
        database: display_text(&project.getattr("effective_target_database")?)?,
        schema: display_text(&project.getattr("effective_target_schema")?)?,
        warehouse,
        concurrency: concurrency.extract()?,
        full_refresh: context.request_flag("full_refresh")?,
        selected_count,
        total_count,
        date_vars: (
            validated_date(py, variable("start_date")?)?,
            validated_date(py, variable("end_date")?)?,
        ),
        selector_files,
    })
}

/// Write the resolved non-secret placement, mode and selection context.
pub(crate) fn write_run_context(
    context: &BuildContext<'_>,
    pipeline: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let concurrency: Bound<'_, PyAny> = context.concurrency(&pipeline.getattr("project")?)?;
    let facts: RunContextFacts = run_context_facts(context, pipeline, &concurrency)?;
    emit(
        &context.stream,
        &render_run_context(
            &facts,
            CliStyle {
                use_color: context.use_color,
            },
        ),
    )
}

fn cursors<'py>(
    context: &BuildContext<'py>,
    plan: &Bound<'py, PyAny>,
) -> PyResult<[Bound<'py, PyAny>; 4]> {
    let py: Python<'py> = context.py();
    let mut overrides: Bound<'py, PyAny> = plan.getattr("cursor_overrides")?;
    if !overrides.is_truthy()? {
        overrides = call_with(
            &imported(py, CURSOR_OVERRIDES_MODULE, "typed_cursor_overrides")?,
            &[(
                "cursor_overrides",
                context.request.getattr("cursor_overrides")?,
            )],
        )?;
    }
    if !overrides.is_truthy()? {
        overrides = imported(py, PLANNER_MODELS, "CursorOverrides")?.call0()?;
    }
    let timestamp: Bound<'py, PyAny> = imported(py, PARSING_MODULE, "parse_cursor_timestamp")?;
    let integer: Bound<'py, PyAny> = imported(py, PARSING_MODULE, "parse_cursor_integer")?;
    Ok([
        timestamp.call1((overrides.getattr("start_ts")?,))?,
        timestamp.call1((overrides.getattr("end_ts")?,))?,
        integer.call1((overrides.getattr("start_int")?,))?,
        integer.call1((overrides.getattr("end_int")?,))?,
    ])
}

/// Build callbacks, the execution header, the execution connection reporter and the Python lifecycle.
pub(crate) fn prepare_build_execution<'py>(
    context: &BuildContext<'py>,
    pipeline: &Bound<'py, PyAny>,
    providers: &Bound<'py, PyAny>,
) -> PyResult<Preparation<'py>> {
    let py: Python<'py> = context.py();
    let plan: Bound<'py, PyAny> = pipeline.getattr("plan_output")?;
    let debug: bool = context.request_flag("debug")? || context.request_flag("json_output")?;
    let callbacks: Bound<'py, PyAny> = call_with(
        &imported(py, CALLBACKS_MODULE, "BuildProgressCallbacks")?,
        &[
            ("plan", plan.clone()),
            ("use_color", boolean(py, context.use_color)),
            ("verbose", context.request.getattr("verbose")?),
            ("debug", boolean(py, debug)),
            (
                "event_output_path",
                context.request.getattr("event_output_path")?,
            ),
        ],
    )?;
    let concurrency: Bound<'py, PyAny> = context.concurrency(&pipeline.getattr("project")?)?;
    if context.verbose {
        write_run_context(context, pipeline)?;
    } else {
        call_with(
            &imported(py, NATIVE_MODULE, "write_execution_header")?,
            &[
                ("stream", context.stream.clone()),
                ("command", text(py, EXECUTION_COMMAND)),
                ("target", none(py)),
                ("concurrency", concurrency.clone()),
                ("use_color", boolean(py, context.use_color)),
            ],
        )?;
    }
    let connection_progress: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "ConnectionProgressReporter")?,
        &[
            ("adapter_name", context.get("adapter_name")?),
            ("stream", context.stream.clone()),
            (
                "blank_line_before_start",
                boolean(py, plan.getattr("source_load_entries")?.is_truthy()?),
            ),
            ("blank_line_after_complete", boolean(py, true)),
            ("use_color", boolean(py, context.use_color)),
        ],
    )?;
    let cursors: [Bound<'py, PyAny>; 4] = cursors(context, &plan)?;
    let inputs: LifecycleInputs<'py> = LifecycleInputs {
        cursors: cursors.clone(),
        on_node_start: keyword_relay(callbacks.getattr("on_node_start")?, &NODE_START)?,
        on_node_complete: callbacks.getattr("on_node_complete")?,
        providers: providers.clone(),
    };
    let lifecycle: Bound<'py, DirectPythonLifecycle> =
        prepare_direct_python_lifecycle(context, pipeline, &inputs)?;
    Ok(Preparation {
        callbacks,
        concurrency,
        connection_progress,
        lifecycle,
        cursors,
    })
}

fn verbose_callback<'py>(
    context: &BuildContext<'py>,
    callbacks: &Bound<'py, PyAny>,
    name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    if context.verbose {
        return callbacks.getattr(name);
    }
    Ok(none(context.py()))
}

/// Run the build pipeline, record eligible source freshness and finalize the Python lifecycle.
pub(crate) fn execute_build_plan<'py>(
    context: &BuildContext<'py>,
    pipeline: &Bound<'py, PyAny>,
    preparation: &Preparation<'py>,
    providers: &Bound<'py, PyAny>,
) -> PyResult<Outcome<'py>> {
    let py: Python<'py> = context.py();
    let plan: Bound<'py, PyAny> = pipeline.getattr("plan_output")?;
    let project: Bound<'py, PyAny> = pipeline.getattr("project")?;
    let adapter: Bound<'py, PyAny> = context.get("adapter")?;
    let connection_config: Bound<'py, PyAny> = context.get("connection_config")?;
    let callbacks: &Bound<'py, PyAny> = &preparation.callbacks;
    let lifecycle: &DirectPythonLifecycle = preparation.lifecycle.get();
    let [start_ts, end_ts, start_int, end_int] = &preparation.cursors;
    let request = |name: &str| context.request.getattr(name);
    let runtime: Bound<'py, PyAny> = call_with(
        &imported(py, BUILD_MODELS, "BuildRuntimeParams")?,
        &[
            ("run_id", project.getattr("run_id")?),
            (
                "runtime_dir",
                joined(&context.get("effective_project_dir")?, &["target"])?,
            ),
            (
                "snapshots",
                context
                    .get("discovered_inputs")?
                    .getattr("project_config")?
                    .getattr("snapshots")?,
            ),
            (
                "allow_snapshot_schema_change",
                request("allow_snapshot_schema_change")?,
            ),
            ("run_tests", request("run_tests")?),
            ("run_audits", request("run_audits")?),
            ("fail_fast", request("fail_fast")?),
            ("max_concurrency", preparation.concurrency.clone()),
            ("loader_is_reload", request("reload_sources")?),
            ("start_cursor_ts", start_ts.clone()),
            ("end_cursor_ts", end_ts.clone()),
            ("start_cursor_int", start_int.clone()),
            ("end_cursor_int", end_int.clone()),
            ("use_color", boolean(py, context.use_color)),
            ("providers", providers.clone()),
            (
                "project_relations",
                call_with(
                    &imported(py, NATIVE_MODULE, "build_project_relation_targets")?,
                    &[("adapter", adapter.clone()), ("plan_output", plan.clone())],
                )?,
            ),
        ],
    )?;
    let connection: &Bound<'py, PyAny> = &preparation.connection_progress;
    let build_callbacks: Bound<'py, PyAny> = call_with(
        &imported(py, BUILD_MODELS, "BuildCallbacks")?,
        &[
            ("on_migration_progress", line_writer(&context.stream)?),
            (
                "on_node_start",
                keyword_relay(callbacks.getattr("on_node_start")?, &NODE_START)?,
            ),
            (
                "on_node_complete",
                preparation.lifecycle.getattr("on_node_complete")?,
            ),
            ("on_sub_progress", callbacks.getattr("on_sub_progress")?),
            (
                "on_connection_start",
                connection.getattr("on_connection_start")?,
            ),
            (
                "on_connection_complete",
                keyword_relay(
                    connection.getattr("on_connection_complete")?,
                    &CONNECTION_TIMING,
                )?,
            ),
            (
                "on_connection_error",
                keyword_relay(
                    connection.getattr("on_connection_error")?,
                    &CONNECTION_TIMING,
                )?,
            ),
            (
                "on_scheduler_state",
                verbose_callback(context, callbacks, "on_scheduler_state")?,
            ),
            (
                "on_statement_complete",
                verbose_callback(context, callbacks, "on_statement_complete")?,
            ),
        ],
    )?;
    let customizations: Bound<'py, PyAny> = call_with(
        &imported(py, BUILD_MODELS, "BuildCustomizations")?,
        &[
            (
                "custom_materializations",
                pipeline.getattr("custom_materializations")?,
            ),
            ("loader_functions", lifecycle.loader_functions(py)?),
        ],
    )?;
    let initial_state: Bound<'py, PyAny> = call_with(
        &imported(py, BUILD_MODELS, "BuildInitialState")?,
        &[
            ("precompleted_keys", lifecycle.precompleted_keys(py)?),
            ("initial_load_results", lifecycle.ingress_load_results(py)),
            ("initial_failed_keys", lifecycle.blocked_keys(py)?),
        ],
    )?;
    let result: Bound<'py, PyAny> = call_with(
        &imported(py, PIPELINE_RUN_MODULE, "run_build_pipeline")?,
        &[
            ("plan", plan.clone()),
            ("connection_config", connection_config.clone()),
            ("adapter", adapter.clone()),
            ("settings", project.getattr("settings")?),
            ("runtime", runtime),
            ("callbacks", build_callbacks),
            ("customizations", customizations),
            ("initial_state", initial_state),
        ],
    )?;
    call_with(
        &imported(
            py,
            FRESHNESS_MODULE,
            "append_eligible_direct_source_freshness_records",
        )?,
        &[
            ("plan", plan),
            ("result", result.clone()),
            ("adapter", adapter),
            ("connection_config", connection_config),
            ("run_id", project.getattr("run_id")?),
        ],
    )?;
    lifecycle.finalize(py)?;
    Ok(Outcome {
        result,
        python_results: lifecycle.python_results(py)?,
    })
}

fn check_runtime<'py>(
    context: &BuildContext<'py>,
    pipeline: &Bound<'py, PyAny>,
    (connection, graph, checks): (&Bound<'py, PyAny>, &Bound<'py, PyAny>, &[Bound<'py, PyAny>]),
    providers: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.py();
    let adapter: Bound<'py, PyAny> = context.get("adapter")?;
    let project: Bound<'py, PyAny> = pipeline.getattr("project")?;
    let names: Vec<Bound<'py, PyAny>> = checks
        .iter()
        .map(|check| check.getattr("name"))
        .collect::<PyResult<_>>()?;
    call_with(
        &imported(py, EXECUTOR_PYTHON_MODELS, "PythonNodeRuntime")?,
        &[
            ("adapter", adapter.clone()),
            ("connection_config", context.get("connection_config")?),
            ("connection", connection.clone()),
            ("run_id", project.getattr("run_id")?),
            ("target", project.getattr("effective_target_name")?),
            ("vars", project.getattr("effective_vars")?),
            ("is_reload", context.request.getattr("reload_sources")?),
            (
                "default_database",
                adapter.call_method0("default_database")?,
            ),
            ("default_schema", adapter.call_method0("default_schema")?),
            (
                "relation_targets",
                call_with(
                    &imported(py, CHECK_CORE_MODULE, "build_check_relation_targets")?,
                    &[
                        ("adapter", adapter.clone()),
                        ("pipeline_result", pipeline.clone()),
                        ("python_graph", graph.clone()),
                        ("selected_python_names", frozenset(py, &names)?),
                    ],
                )?,
            ),
            (
                "project_relations",
                call_with(
                    &imported(py, NATIVE_MODULE, "build_project_relation_targets")?,
                    &[
                        ("adapter", adapter),
                        ("plan_output", pipeline.getattr("plan_output")?),
                    ],
                )?,
            ),
            ("providers", providers.clone()),
        ],
    )
}

fn names_of<'py>(values: &Bound<'py, PyAny>, attribute: &str) -> PyResult<Vec<Bound<'py, PyAny>>> {
    values
        .try_iter()?
        .map(|value| value?.getattr(attribute))
        .collect()
}

/// Execute relevant Python check functions after a successful build.
pub(crate) fn run_post_build_python_checks<'py>(
    context: &BuildContext<'py>,
    pipeline: &Bound<'py, PyAny>,
    (outcome, preparation): (&Outcome<'py>, &Preparation<'py>),
    providers: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.py();
    let result: &Bound<'py, PyAny> = &outcome.result;
    if result.getattr("status")?.str()?.extract::<String>()? != SUCCESS_STATUS {
        return tuple(py, &[]);
    }
    let discovered: Bound<'py, PyAny> = context.get("discovered_inputs")?;
    let plan: Bound<'py, PyAny> = pipeline.getattr("plan_output")?;
    let load_results: Bound<'py, PyAny> = result.getattr("load_results")?;
    let graph: Bound<'py, PyAny> = call_with(
        &imported(py, GRAPH_MODULE, "build_discovered_python_node_graph")?,
        &[("discovered_inputs", discovered.clone())],
    )?;
    let by_loader = || {
        call_with(
            &imported(py, CHECK_CORE_MODULE, "load_results_by_loader_name")?,
            &[
                ("source_map", plan.getattr("source_map")?),
                ("load_results", load_results.clone()),
            ],
        )
    };
    let mut dependencies: Vec<Bound<'py, PyAny>> = names_of(&outcome.python_results, "node_name")?;
    for name in by_loader()?.try_iter()? {
        dependencies.push(name?);
    }
    let mut completed: Vec<Bound<'py, PyAny>> =
        names_of(&result.getattr("model_results")?, "model_name")?;
    completed.extend(names_of(&result.getattr("seed_results")?, "seed_name")?);
    completed.extend(names_of(&load_results, "source_name")?);
    let checks: Vec<Bound<'py, PyAny>> = call_with(
        &imported(py, CHECK_CORE_MODULE, "relevant_check_functions")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("python_graph", graph.clone()),
            ("exclude", context.request.getattr("exclude")?),
            ("selected_dependency_names", frozenset(py, &dependencies)?),
            ("completed_sql_names", frozenset(py, &completed)?),
        ],
    )?
    .try_iter()?
    .collect::<PyResult<_>>()?;
    if checks.is_empty() {
        return tuple(py, &[]);
    }
    let adapter: Bound<'py, PyAny> = context.get("adapter")?;
    let connection: Bound<'py, PyAny> =
        adapter.call_method1("connect", (context.get("connection_config")?,))?;
    let executed: PyResult<Bound<'py, PyAny>> = (|| {
        let run_state: Bound<'py, PyAny> =
            imported(py, EXECUTOR_PYTHON_MODELS, "PythonNodeRunState")?.call0()?;
        call_with(
            &imported(py, CHECK_CORE_MODULE, "record_python_run_state_results")?,
            &[
                ("discovered_inputs", discovered.clone()),
                ("run_state", run_state.clone()),
                ("python_results", outcome.python_results.clone()),
                ("load_results", load_results.clone()),
                ("source_map", plan.getattr("source_map")?),
            ],
        )?;
        let callbacks: Bound<'py, PyAny> = call_with(
            &imported(py, EXECUTOR_PYTHON_MODELS, "PythonCheckCallbacks")?,
            &[(
                "on_check_complete",
                preparation.callbacks.getattr("write_execution_event")?,
            )],
        )?;
        call_with(
            &imported(py, CHECKS_MODULE, "execute_python_checks")?,
            &[
                ("check_functions", tuple(py, &checks)?),
                ("python_graph", graph.clone()),
                ("upstream_python_results", outcome.python_results.clone()),
                ("upstream_load_results", load_results.clone()),
                ("upstream_load_results_by_loader_name", by_loader()?),
                (
                    "runtime",
                    check_runtime(context, pipeline, (&connection, &graph, &checks), providers)?,
                ),
                ("run_state", run_state),
                ("callbacks", callbacks),
            ],
        )
    })();
    let closed: PyResult<Bound<'py, PyAny>> = adapter.call_method1("close", (connection,));
    let check_results: Bound<'py, PyAny> = executed?;
    closed?;
    call_with(
        &imported(py, NATIVE_MODULE, "write_check_results")?,
        &[
            ("stream", context.stream.clone()),
            ("results", check_results.clone()),
            ("use_color", boolean(py, context.use_color)),
            ("check_functions", tuple(py, &checks)?),
            ("python_graph", graph),
        ],
    )?;
    Ok(check_results)
}

/// Run the prepared build and its checks inside the run cost context.
pub(crate) fn execute_direct_build<'py>(
    context: &BuildContext<'py>,
    pipeline: &Bound<'py, PyAny>,
    providers: &Bound<'py, PyAny>,
) -> PyResult<(Preparation<'py>, Outcome<'py>, Bound<'py, PyAny>)> {
    let py: Python<'py> = context.py();
    let project: Bound<'py, PyAny> = pipeline.getattr("project")?;
    let run_id: Bound<'py, PyAny> = project.getattr("run_id")?;
    let target_name: Bound<'py, PyAny> = project.getattr("effective_target_name")?;
    let resource_name: Bound<'py, PyAny> = if target_name.is_truthy()? {
        target_name
    } else {
        context.get("adapter_name")?
    };
    let cost_context: Bound<'py, PyAny> = imported(py, COST_CONTEXT_MODULE, "CostContext")?;
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("run_id", &run_id)?;
    options.set_item("resource_type", "run")?;
    options.set_item("resource_name", &resource_name)?;
    options.set_item(
        "ledger_path",
        joined(
            &context.get("effective_project_dir")?,
            &[
                "target",
                "executions",
                &run_id.str()?.extract::<String>()?,
                "statements.jsonl",
            ],
        )?,
    )?;
    options.set_item("phase", "build")?;
    let scope: Bound<'py, PyAny> = cost_context.call_method("scope", (), Some(&options))?;
    within(&scope, |_| {
        let preparation: Preparation<'py> = prepare_build_execution(context, pipeline, providers)?;
        let ran: PyResult<(Outcome<'py>, Bound<'py, PyAny>)> = (|| {
            let outcome: Outcome<'py> =
                execute_build_plan(context, pipeline, &preparation, providers)?;
            let checks_scope: Bound<'py, PyAny> = call_with(
                &cost_context.getattr("resource_scope")?,
                &[
                    ("resource_type", text(py, "run")),
                    ("resource_name", resource_name.clone()),
                    ("phase", text(py, "post_build_checks")),
                ],
            )?;
            let checks: Bound<'py, PyAny> = within(&checks_scope, |_| {
                run_post_build_python_checks(context, pipeline, (&outcome, &preparation), providers)
            })?;
            Ok((outcome, checks))
        })();
        let closed: PyResult<Bound<'py, PyAny>> = preparation.callbacks.call_method0("close");
        let (outcome, checks) = ran?;
        closed?;
        Ok((preparation, outcome, checks))
    })
}
