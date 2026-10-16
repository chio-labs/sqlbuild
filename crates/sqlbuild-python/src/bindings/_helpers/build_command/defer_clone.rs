//! `sqb build --defer-clone-from`: clone out-of-selection boundaries before build planning.

use std::time::Instant;

use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyCFunction, PyDict, PyFrozenSet, PyString, PyTuple, PyTupleMethods};
use pyo3::{IntoPyObject, IntoPyObjectExt, pyfunction, wrap_pyfunction};
use sqlbuild_core::build_command::constants::EXECUTION_LIMIT_BUILD_NOTE;

use sqlbuild_core::build_command::errors::BuildCommandError;

use crate::bindings::_helpers::build_command::invocation::BuildContext;
use crate::bindings::_helpers::build_command::policies::build_command_error;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const CLONE_MODELS: &str = "sqlbuild.executor.clone.models";
const CLONE_TYPES: &str = "sqlbuild.executor.clone.types";
const SPEC_TYPES: &str = "sqlbuild._native";
const TRANSIENT_MODELS_MODULE: &str =
    "sqlbuild.executor.clone.main._build_destination_transient_models";
const RETENTION_REQUESTS_MODULE: &str = "sqlbuild.executor.clone.main._build_retention_requests";
const EXECUTE_CLONE_MODULE: &str = "sqlbuild.executor.clone.main.execute";
const FINGERPRINTING_MODULE: &str = "sqlbuild.executor.clone.main._fingerprinting";
const CLONE_STREAM_MODULE: &str = "sqlbuild.executor.clone.main._run_prephase_clone_stream";
const VIEW_MATERIALIZATION: &str = "view";
const RECREATED_TYPES: [&str; 2] = ["udf", "table_fn"];
const CLONABLE_TYPES: [&str; 4] = ["model", "seed", "udf", "table_fn"];
const MODEL_TYPE: &str = "model";

fn text<'py>(py: Python<'py>, value: &str) -> Bound<'py, PyAny> {
    PyString::new(py, value).into_any()
}

fn user_error(py: Python<'_>, message: String, code: &str) -> PyErr {
    build_command_error(
        py,
        BuildCommandError {
            code: Some(code.to_owned()),
            message,
            help: None,
        },
    )
}

fn resource_type(key: &Bound<'_, PyAny>) -> PyResult<String> {
    key.getattr("resource_type")?.getattr("value")?.extract()
}

/// Functions and view models are recreated over cloned boundaries instead of cloned.
fn recreated_over_clones(scope: &Bound<'_, PyAny>, key: &Bound<'_, PyAny>) -> PyResult<bool> {
    if RECREATED_TYPES.contains(&resource_type(key)?.as_str()) {
        return Ok(true);
    }
    let model: Bound<'_, PyAny> = scope
        .getattr("models_by_name")?
        .call_method1("get", (key.getattr("name")?,))?;
    if model.is_none() {
        return Ok(false);
    }
    let materialized: Bound<'_, PyAny> = model
        .getattr("config")?
        .getattr("values")?
        .call_method1("get", ("materialized", VIEW_MATERIALIZATION))?;
    let lowered: String = materialized.str()?.call_method0("lower")?.extract()?;
    Ok(lowered == VIEW_MATERIALIZATION)
}

/// Every key the scope's traversal can visit: the selection and the upstream graph.
fn scope_keys<'py>(scope: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut keys: Vec<Bound<'py, PyAny>> = scope
        .getattr("selected_keys")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    for item in scope
        .getattr("upstream_deps")?
        .call_method0("items")?
        .try_iter()?
    {
        let (key, upstream): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        keys.push(key);
        for upstream_key in upstream.try_iter()? {
            keys.push(upstream_key?);
        }
    }
    Ok(keys)
}

/// `frozenset.__contains__` over the keys a predicate accepts, as the traversal callback.
fn membership<'py>(
    py: Python<'py>,
    keys: &[Bound<'py, PyAny>],
    accepted: impl Fn(&Bound<'py, PyAny>) -> PyResult<bool>,
) -> PyResult<Bound<'py, PyAny>> {
    let mut members: Vec<Bound<'py, PyAny>> = Vec::new();
    for key in keys {
        if accepted(key)? {
            members.push(key.clone());
        }
    }
    PyFrozenSet::new(py, &members)?.getattr("__contains__")
}

fn traversed_names<'py>(
    scope: &Bound<'py, PyAny>,
    (module, function): (&str, &str),
    (is_clonable, is_view): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Vec<String>> {
    let py: Python<'py> = scope.py();
    let keys: Bound<'py, PyAny> = call_with(
        &imported(py, module, function)?,
        &[
            ("selected", scope.getattr("selected_keys")?),
            ("upstream", scope.getattr("upstream_deps")?),
            ("is_clonable", is_clonable.clone()),
            ("is_view", is_view.clone()),
        ],
    )?;
    let mut names: Vec<String> = Vec::new();
    for key in keys.try_iter()? {
        names.push(key?.getattr("name")?.extract()?);
    }
    names.sort();
    Ok(names)
}

/// Selected models except those explicitly disabled.
fn selected_executable_model_count(scope: &Bound<'_, PyAny>) -> PyResult<usize> {
    let models: Bound<'_, PyAny> = scope.getattr("models_by_name")?;
    let mut count: usize = 0;
    for key in scope.getattr("selected_keys")?.try_iter()? {
        let key: Bound<'_, PyAny> = key?;
        if resource_type(&key)? != MODEL_TYPE {
            continue;
        }
        let model: Bound<'_, PyAny> = models.call_method1("get", (key.getattr("name")?,))?;
        if !model.is_none()
            && model
                .getattr("config")?
                .getattr("values")?
                .call_method1("get", ("enabled",))?
                .is(false.into_pyobject(scope.py())?.to_owned().into_any())
        {
            continue;
        }
        count += 1;
    }
    Ok(count)
}

/// Boundary clone selectors, rebuilt view-chain selectors and the selected model count.
fn defer_clone_selection(scope: &Bound<'_, PyAny>) -> PyResult<(Vec<String>, Vec<String>, usize)> {
    let py: Python<'_> = scope.py();
    let keys: Vec<Bound<'_, PyAny>> = scope_keys(scope)?;
    let is_clonable: Bound<'_, PyAny> = membership(py, &keys, |key| {
        Ok(CLONABLE_TYPES.contains(&resource_type(key)?.as_str()))
    })?;
    let is_view: Bound<'_, PyAny> = membership(py, &keys, |key| recreated_over_clones(scope, key))?;
    let callbacks: (&Bound<'_, PyAny>, &Bound<'_, PyAny>) = (&is_clonable, &is_view);
    Ok((
        traversed_names(scope, (NATIVE_MODULE, "resolve_clone_boundary"), callbacks)?,
        traversed_names(
            scope,
            (NATIVE_MODULE, "resolve_skipped_view_chain"),
            callbacks,
        )?,
        selected_executable_model_count(scope)?,
    ))
}

/// Boundary selectors, view-chain selectors and selected executable model count of a scope.
#[pyfunction]
#[pyo3(signature = (*, scope))]
fn resolve_defer_clone_selection(
    scope: &Bound<'_, PyAny>,
) -> PyResult<(Vec<String>, Vec<String>, usize)> {
    defer_clone_selection(scope)
}

fn native<'py>(
    py: Python<'py>,
    name: &str,
    fields: &[(&str, Bound<'py, PyAny>)],
) -> PyResult<Bound<'py, PyAny>> {
    call_with(&imported(py, NATIVE_MODULE, name)?, fields)
}

fn external_resolver<'py>(
    project_dir: &Bound<'py, PyAny>,
    discovered: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    native(
        project_dir.py(),
        "resolve_external_sql_reference_resolver",
        &[
            ("project_dir", project_dir.clone()),
            ("discovered_inputs", discovered.clone()),
        ],
    )
}

/// The resolved defer-clone prephase: what to clone, from where, into which target.
struct Prephase<'py> {
    discovered: Bound<'py, PyAny>,
    adapter: Bound<'py, PyAny>,
    origin: Bound<'py, PyAny>,
    destination: Bound<'py, PyAny>,
    select: Vec<String>,
    caused_by: Bound<'py, PyAny>,
    project_dir: Bound<'py, PyAny>,
}

fn progress(on_progress: &Bound<'_, PyAny>, message: &str) -> PyResult<()> {
    if !on_progress.is_none() {
        on_progress.call1((message,))?;
    }
    Ok(())
}

fn clone_input<'py>(
    context: &BuildContext<'py>,
    prephase: &Prephase<'py>,
    (pipeline, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    on_item: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.py();
    let project: Bound<'py, PyAny> = pipeline.getattr("destination_project")?;
    let destination_models: Bound<'py, PyAny> = pipeline.getattr("destination_model_entries")?;
    let target: Bound<'py, PyAny> = native(
        py,
        "resolve_target_config",
        &[
            (
                "project_config",
                prephase.discovered.getattr("project_config")?,
            ),
            ("local_config", prephase.discovered.getattr("local_config")?),
            ("target_name", prephase.destination.clone()),
        ],
    )?;
    let mut selected: Vec<Bound<'py, PyAny>> = Vec::new();
    for entry in destination_models.try_iter()? {
        selected.push(entry?.getattr("name")?);
    }
    let retention: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            RETENTION_REQUESTS_MODULE,
            "build_destination_retention_requests",
        )?,
        &[
            ("project", project.clone()),
            ("adapter_name", prephase.adapter.getattr("adapter_name")?),
            (
                "selected_model_names",
                PyFrozenSet::new(py, &selected)?.into_any(),
            ),
            (
                "namespace_owned",
                target.getattr("owns_time_travel_retention_namespace")?,
            ),
        ],
    )?;
    let allow_decrease: bool = target
        .getattr("time_travel_retention_decrease")?
        .eq(imported(py, SPEC_TYPES, "RetentionDecreasePolicy")?.getattr("ALLOW")?)?;
    let sources: Bound<'py, PyAny> = call_with(
        &imported(py, CLONE_MODELS, "CloneSourceEntries")?,
        &[
            ("origin", pipeline.getattr("origin_source_entries")?),
            (
                "destination",
                pipeline.getattr("destination_source_entries")?,
            ),
        ],
    )?;
    call_with(
        &imported(py, CLONE_MODELS, "CloneExecutionInput")?,
        &[
            ("source_entries", sources),
            (
                "origin_model_entries",
                pipeline.getattr("origin_model_entries")?,
            ),
            ("destination_model_entries", destination_models),
            (
                "origin_seed_entries",
                pipeline.getattr("origin_seed_entries")?,
            ),
            (
                "destination_seed_entries",
                pipeline.getattr("destination_seed_entries")?,
            ),
            (
                "destination_function_entries",
                pipeline.getattr("destination_function_entries")?,
            ),
            (
                "execution_order",
                pipeline.getattr("clone_plan")?.getattr("execution_order")?,
            ),
            ("adapter", prephase.adapter.clone()),
            ("destination_connection", connection.clone()),
            ("hard_copy", false.into_pyobject(py)?.to_owned().into_any()),
            ("run_id", project.getattr("run_id")?),
            (
                "query_change_tracking",
                project
                    .getattr("settings")?
                    .getattr("query_change_tracking")?,
            ),
            (
                "destination_transient_models",
                call_with(
                    &imported(
                        py,
                        TRANSIENT_MODELS_MODULE,
                        "build_destination_transient_models",
                    )?,
                    &[("project", project.clone())],
                )?,
            ),
            ("destination_retention_requests", retention),
            (
                "allow_namespace_retention_decrease",
                allow_decrease.into_pyobject(py)?.to_owned().into_any(),
            ),
            ("on_item", on_item),
        ],
    )
}

/// Execute the clone, through the prephase progress stream when there is one.
fn executed_clone<'py>(
    context: &BuildContext<'py>,
    prephase: &Prephase<'py>,
    (pipeline, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = context.py();
    let progress_stream: Bound<'py, PyAny> = context.invocation.getattr("progress_stream")?;
    let execute: Bound<'py, PyAny> = imported(py, EXECUTE_CLONE_MODULE, "execute_clone")?;
    if progress_stream.is_none() {
        let inputs: Bound<'py, PyAny> = clone_input(
            context,
            prephase,
            (pipeline, connection),
            py.None().into_bound(py),
        )?;
        return call_with(&execute, &[("inputs", inputs)]);
    }
    let prepared: (Py<PyAny>, Py<PyAny>) = (
        clone_input(
            context,
            prephase,
            (pipeline, connection),
            py.None().into_bound(py),
        )?
        .unbind(),
        execute.unbind(),
    );
    let run_clone: Bound<'py, PyCFunction> = PyCFunction::new_closure(
        py,
        None,
        None,
        move |arguments: &Bound<'_, PyTuple>,
              _: Option<&Bound<'_, PyDict>>|
              -> PyResult<Py<PyAny>> {
            let py: Python<'_> = arguments.py();
            let inputs: Bound<'_, PyAny> = imported(py, "dataclasses", "replace")?.call(
                (prepared.0.bind(py),),
                Some(&keywords(py, &[("on_item", arguments.get_item(0)?)])?),
            )?;
            Ok(prepared
                .1
                .bind(py)
                .call((), Some(&keywords(py, &[("inputs", inputs)])?))?
                .unbind())
        },
    )?;
    call_with(
        &imported(py, CLONE_STREAM_MODULE, "run_prephase_clone_stream")?,
        &[
            ("stream", progress_stream),
            ("title", text(py, "defer clone")),
            ("caused_by_names", prephase.caused_by.clone()),
            ("use_color", context.invocation.getattr("use_color")?),
            ("run_clone", run_clone.into_any()),
        ],
    )
}

fn failed_items(result: &Bound<'_, PyAny>) -> PyResult<Vec<String>> {
    let py: Python<'_> = result.py();
    let status: Bound<'_, PyAny> = imported(py, CLONE_TYPES, "CloneStatus")?;
    let (failed, warning) = (status.getattr("FAILED")?, status.getattr("WARNING")?);
    let mut items: Vec<String> = Vec::new();
    for item in result.getattr("item_results")?.try_iter()? {
        let item: Bound<'_, PyAny> = item?;
        let item_status: Bound<'_, PyAny> = item.getattr("status")?;
        if !(item_status.eq(&failed)? || item_status.eq(&warning)?) {
            continue;
        }
        let message: Bound<'_, PyAny> = item.getattr("message")?;
        let detail: Bound<'_, PyAny> = if message.is_truthy()? {
            message
        } else {
            item.getattr("action")?.getattr("value")?
        };
        items.push(format!(
            "{}: {}",
            item.getattr("name")?.str()?,
            detail.str()?
        ));
    }
    Ok(items)
}

/// Clone the boundary relations from the origin target, then copy their fingerprints.
fn clone_boundaries<'py>(
    context: &BuildContext<'py>,
    prephase: &Prephase<'py>,
    connection: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let py: Python<'py> = context.py();
    let on_progress: Bound<'py, PyAny> = context
        .invocation
        .getattr("planning_progress")?
        .getattr("on_progress")?;
    let start: Instant = Instant::now();
    let request: &Bound<'py, PyAny> = &context.request;
    let pipeline: Bound<'py, PyAny> = native(
        py,
        "run_clone_pipeline_with_options",
        &[
            ("discovered_inputs", prephase.discovered.clone()),
            ("adapter", prephase.adapter.clone()),
            ("origin_target_name", prephase.origin.clone()),
            ("destination_target_name", prephase.destination.clone()),
            (
                "destination_connection",
                call_with(
                    &imported(py, NATIVE_RECORDS_MODULE, "ClonePipelineConnection")?,
                    &[
                        ("config", context.invocation.getattr("connection_config")?),
                        ("handle", connection.clone()),
                    ],
                )?,
            ),
            (
                "options",
                call_with(
                    &imported(py, NATIVE_RECORDS_MODULE, "ClonePipelineOptions")?,
                    &[
                        ("no_sql_validation", request.getattr("no_sql_validation")?),
                        ("no_cache", request.getattr("no_cache")?),
                        ("select", PyTuple::new(py, &prephase.select)?.into_any()),
                        ("cli_vars", request.getattr("cli_vars")?),
                    ],
                )?,
            ),
            (
                "external_sql_reference_resolver",
                external_resolver(&prephase.project_dir, &prephase.discovered)?,
            ),
        ],
    )?;
    progress(
        &on_progress,
        &format!(
            "Prepared defer clone plan. ({:.2}s)",
            start.elapsed().as_secs_f64()
        ),
    )?;
    let result: Bound<'py, PyAny> = executed_clone(context, prephase, (&pipeline, connection))?;
    let failed: Vec<String> = failed_items(&result)?;
    if !failed.is_empty() {
        return Err(user_error(
            py,
            format!(
                "failed to clone one or more deferred boundary relations: {}",
                failed.join("; ")
            ),
            "C411",
        ));
    }
    let project: Bound<'py, PyAny> = pipeline.getattr("destination_project")?;
    call_with(
        &imported(py, FINGERPRINTING_MODULE, "copy_clone_fingerprints")?,
        &[
            ("result", result),
            (
                "origin_model_entries",
                pipeline.getattr("origin_model_entries")?,
            ),
            (
                "destination_model_entries",
                pipeline.getattr("destination_model_entries")?,
            ),
            (
                "origin_seed_entries",
                pipeline.getattr("origin_seed_entries")?,
            ),
            (
                "destination_seed_entries",
                pipeline.getattr("destination_seed_entries")?,
            ),
            ("adapter", prephase.adapter.clone()),
            ("destination_connection", connection.clone()),
            ("run_id", project.getattr("run_id")?),
            (
                "query_change_tracking",
                project
                    .getattr("settings")?
                    .getattr("query_change_tracking")?,
            ),
        ],
    )?;
    Ok(())
}

/// Clone the selected boundary relations from the origin before build planning.
fn run_prephase(context: &BuildContext<'_>, prephase: &Prephase<'_>) -> PyResult<()> {
    let py: Python<'_> = context.py();
    if prephase.select.is_empty() {
        return Ok(());
    }
    if prephase.destination.is_none() {
        return Err(user_error(
            py,
            "--defer-clone-from requires an active target".to_owned(),
            "C409",
        ));
    }
    if prephase.origin.eq(&prephase.destination)? {
        return Err(user_error(
            py,
            format!(
                "Cannot defer-clone from the current target '{}'",
                prephase.origin.str()?
            ),
            "C410",
        ));
    }
    progress(
        &context
            .invocation
            .getattr("planning_progress")?
            .getattr("on_progress")?,
        "Preparing defer clone plan...",
    )?;
    let connection: Bound<'_, PyAny> = prephase.adapter.call_method1(
        "connect",
        (context.invocation.getattr("connection_config")?,),
    )?;
    let cloned: PyResult<()> = clone_boundaries(context, prephase, &connection);
    prephase.adapter.call_method1("close", (connection,))?;
    cloned
}

/// Resolve defer-clone boundaries and clone them before build planning.
pub(crate) fn run_defer_clone_boundary_prephase(
    context: &BuildContext<'_>,
    origin: Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = context.py();
    let (request, invocation) = (&context.request, &context.invocation);
    let discovered: Bound<'_, PyAny> = invocation.getattr("discovered_inputs")?;
    let split: Bound<'_, PyAny> = native(
        py,
        "split_unit_test_selectors",
        &[
            ("select", request.getattr("select")?),
            ("exclude", request.getattr("exclude")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    if !split
        .getattr("sql_test_selection")?
        .getattr("models_selected")?
        .is_truthy()?
    {
        return Ok(());
    }
    let adapter: Bound<'_, PyAny> = invocation.getattr("adapter")?;
    let project_dir: Bound<'_, PyAny> = invocation.getattr("effective_project_dir")?;
    let project: Bound<'_, PyAny> = native(
        py,
        "build_compiled_project",
        &[
            ("discovered_inputs", discovered.clone()),
            ("adapter", adapter.clone()),
            ("selected_target", request.getattr("selected_target")?),
            ("no_sql_validation", request.getattr("no_sql_validation")?),
            (
                "analysis_selection",
                call_with(
                    &imported(py, NATIVE_RECORDS_MODULE, "CompileAnalysisSelection")?,
                    &[("no_cache", request.getattr("no_cache")?)],
                )?,
            ),
            ("cli_vars", request.getattr("cli_vars")?),
            (
                "external_sql_reference_resolver",
                external_resolver(&project_dir, &discovered)?,
            ),
        ],
    )?;
    let scope: Bound<'_, PyAny> = native(
        py,
        "build_planner_scope",
        &[
            ("project", project.clone()),
            ("select", split.getattr("select")?),
            ("exclude", split.getattr("exclude")?),
            (
                "auto_load_sources",
                invocation.getattr("should_load_sources")?,
            ),
        ],
    )?;
    let (boundary, view_chain, model_count): (Vec<String>, Vec<String>, usize) =
        defer_clone_selection(&scope)?;
    native(
        py,
        "enforce_model_execution_limit",
        &[
            ("model_count", model_count.into_pyobject(py)?.into_any()),
            ("target_name", invocation.getattr("effective_target_name")?),
            ("limits", invocation.getattr("execution_limits")?),
            (
                "refusal_note",
                EXECUTION_LIMIT_BUILD_NOTE.into_bound_py_any(py)?,
            ),
        ],
    )?;
    let mut select: Vec<String> = boundary;
    select.extend(view_chain);
    run_prephase(
        context,
        &Prephase {
            discovered,
            adapter,
            origin,
            destination: project.getattr("effective_target_name")?,
            select,
            caused_by: split.getattr("select")?,
            project_dir,
        },
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resolve_defer_clone_selection, module)?)
}
