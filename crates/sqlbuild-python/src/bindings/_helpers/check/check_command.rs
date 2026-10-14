//! `sqb check`: run the selected Python checks after their Python dependencies.

use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyFrozenSet, PyInt, PyString, PyTuple};
use pyo3::{pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_core::check_command::errors::CheckSelectionError;
use sqlbuild_core::check_command::main::check_exit_code::check_exit_code;
use sqlbuild_core::check_command::main::render_check_summary::render_check_summary;
use sqlbuild_core::check_command::main::validate_check_selection::validate_check_selection;
use sqlbuild_core::check_command::models::CheckResultText;
use sqlbuild_core::cli_text::models::CliStyle;

use crate::bindings::_helpers::check::check_results::{
    check_result_text, results_json, write_results,
};
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::graph::python_selection::python_node_names;

const NATIVE_MODULE: &str = "sqlbuild._native";
const ERRORS_MODULE: &str = "sqlbuild.cli.commands.exceptions";
const COMMAND_MODELS: &str = "sqlbuild.cli.commands.models";
const INVOCATION_MODULE: &str = "sqlbuild.cli.commands._helpers.runtime.command_invocation";
const CHECK_CORE_MODULE: &str = "sqlbuild.cli.commands._helpers.check.core";
const EXTERNAL_REFS_MODULE: &str = "sqlbuild.cli.commands._helpers.planning.external_refs";
const REJECT_UNIT_TESTS_MODULE: &str = "sqlbuild.compiler.pipeline.main.reject_unit_test_selectors";
const STATIC_COMMAND_MODULE: &str = "sqlbuild._native";
const PIPELINE_MODELS: &str = "sqlbuild.compiler.pipeline.models";
const RELATION_PLAN_MODULE: &str = "sqlbuild.compiler.planner.main.commands._relation_plan";
const SELECTOR_PARSE_MODULE: &str = "sqlbuild.compiler.planner.main.selection.selector_parse";
const PLANNER_MODELS: &str = "sqlbuild.compiler.planner.models";
const COMPILE_MODELS: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES: &str = "sqlbuild.compiler.compile.types";
const PYTHON_GRAPH_MODULE: &str = "sqlbuild.compiler.python_nodes.main._graph";
const PYTHON_NODE_MODELS: &str = "sqlbuild.compiler.python_nodes.models";
const PYTHON_NODE_TYPES: &str = "sqlbuild.compiler.python_nodes.types";
const EXECUTOR_MODELS: &str = "sqlbuild.executor.python_nodes.models";
const CHECKS_MODULE: &str = "sqlbuild.executor.python_nodes.main._checks";
const INGRESS_MODULE: &str = "sqlbuild.executor.python_nodes.main._ingress";
const PROVIDER_SESSION_MODULE: &str = "sqlbuild.provider.main.session";
const RUNTIME_TARGET_MODULE: &str =
    "sqlbuild.cli.target_artifacts.main._write_python_check_runtime_target";
const GRAPH_OPERATOR_CODE: &str = "C681";
const GRAPH_OPERATOR_MESSAGE: &str = "sqb check selectors do not support graph operators; \
    select checks directly without '+', '~', or path-between expansion";
const EXECUTION_COMMAND: &str = "sqb check";

/// The compiled pipeline and everything checks run with.
struct Prepared<'py> {
    pipeline: Bound<'py, PyAny>,
    python_graph: Bound<'py, PyAny>,
    check_functions: Bound<'py, PyAny>,
    lifecycle_plan: Bound<'py, PyAny>,
    relation_targets: Bound<'py, PyAny>,
    relation_refs: Bound<'py, PyAny>,
    defaults: (Bound<'py, PyAny>, Bound<'py, PyAny>),
    project_relations: Bound<'py, PyAny>,
}

fn user_error(py: Python<'_>, (code, message): (&str, &str)) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", code)?;
        imported(py, ERRORS_MODULE, "CliUserError")?.call((message,), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

fn selection_error(py: Python<'_>, error: &CheckSelectionError) -> PyErr {
    user_error(py, (error.code, &error.message))
}

fn empty_tuple(py: Python<'_>) -> Bound<'_, PyAny> {
    PyTuple::empty(py).into_any()
}

/// Refuse `+`, `~` and path selectors, splitting selectors as Python's `split` does.
fn refuse_graph_selectors(py: Python<'_>, selectors: &[Bound<'_, PyAny>]) -> PyResult<()> {
    let parse: Bound<'_, PyAny> = imported(py, SELECTOR_PARSE_MODULE, "parse_project_selector")?;
    let path_selector: Bound<'_, PyAny> = imported(py, PLANNER_MODELS, "PathSelector")?;
    for selector in selectors {
        for token in selector.call_method0("split")?.try_iter()? {
            for part in token?.call_method1("split", (",",))?.try_iter()? {
                let parsed: Bound<'_, PyAny> = parse.call1((part?,))?;
                if parsed.is_instance(&path_selector)?
                    || parsed.getattr("upstream")?.is_truthy()?
                    || parsed.getattr("downstream")?.is_truthy()?
                {
                    return Err(user_error(
                        py,
                        (GRAPH_OPERATOR_CODE, GRAPH_OPERATOR_MESSAGE),
                    ));
                }
            }
        }
    }
    Ok(())
}

fn python_nodes<'py>(
    graph: &Bound<'py, PyAny>,
    (select, exclude): (Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    Ok(python_node_names(graph, (select.extract()?, exclude.extract()?))?.into_any())
}

fn node_kind<'py>(
    graph: &Bound<'py, PyAny>,
    name: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    graph
        .getattr("nodes_by_name")?
        .get_item(name)?
        .getattr("kind")
}

/// The selected check names: selected checks, or every check minus excluded nodes.
fn selected_check_names<'py>(
    request: &Bound<'py, PyAny>,
    graph: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let py: Python<'py> = graph.py();
    let select: Bound<'py, PyAny> = request.getattr("select")?;
    let exclude: Bound<'py, PyAny> = request.getattr("exclude")?;
    let selectors: Vec<Bound<'py, PyAny>> = select
        .try_iter()?
        .chain(exclude.try_iter()?)
        .collect::<PyResult<_>>()?;
    refuse_graph_selectors(py, &selectors)?;
    let check_kind: Bound<'py, PyAny> =
        imported(py, PYTHON_NODE_TYPES, "PythonNodeKind")?.getattr("CHECK")?;
    if select.is_truthy()? {
        let selected: Bound<'py, PyAny> = python_nodes(graph, (select, exclude))?;
        let mut non_checks: Vec<String> = Vec::new();
        for name in selected.try_iter()? {
            let name: Bound<'py, PyAny> = name?;
            if !node_kind(graph, &name)?.eq(&check_kind)? {
                non_checks.push(name.extract()?);
            }
        }
        validate_check_selection(&non_checks).map_err(|error| selection_error(py, &error))?;
        return selected.downcast_into().map_err(Into::into);
    }
    let excluded: Bound<'py, PyAny> = if exclude.is_truthy()? {
        python_nodes(graph, (exclude, empty_tuple(py)))?
    } else {
        PyFrozenSet::empty(py)?.into_any()
    };
    let mut names: Vec<Bound<'py, PyAny>> = Vec::new();
    for node in graph.getattr("nodes")?.try_iter()? {
        let node: Bound<'py, PyAny> = node?;
        let name: Bound<'py, PyAny> = node.getattr("name")?;
        if node.getattr("kind")?.eq(&check_kind)? && !excluded.contains(&name)? {
            names.push(name);
        }
    }
    PyFrozenSet::new(py, names)
}

/// Compile the SQL relations and loader sources the selected checks depend on.
fn compile_pipeline<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Bound<'py, PyAny>,
    (graph, check_names): (&Bound<'py, PyAny>, &Bound<'py, PyFrozenSet>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let discovered: Bound<'py, PyAny> = invocation.getattr("discovered_inputs")?;
    let required_refs: Bound<'py, PyAny> = call_with(
        &graph.getattr("selected_sql_refs")?,
        &[("selected_names", check_names.clone().into_any())],
    )?;
    let closure: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "transitive_closure_many")?,
        &[
            ("starts", check_names.clone().into_any()),
            ("edges", graph.getattr("upstream_deps")?),
            (
                "include_starts",
                PyBool::new(py, false).to_owned().into_any(),
            ),
        ],
    )?;
    let loader_kind: Bound<'py, PyAny> =
        imported(py, PYTHON_NODE_TYPES, "PythonNodeKind")?.getattr("LOADER")?;
    let mut loaders: Vec<Bound<'py, PyAny>> = Vec::new();
    for name in closure.try_iter()? {
        let name: Bound<'py, PyAny> = name?;
        if !check_names.contains(&name)? && node_kind(graph, &name)?.eq(&loader_kind)? {
            loaders.push(name);
        }
    }
    let loaders: Bound<'py, PyFrozenSet> = PyFrozenSet::new(py, loaders)?;
    let key_class: Bound<'py, PyAny> = imported(py, COMPILE_MODELS, "CompiledObjectKey")?;
    let source_type: Bound<'py, PyAny> =
        imported(py, COMPILE_TYPES, "CompiledResourceType")?.getattr("SOURCE")?;
    let ref_key: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "sql_ref_key")?;
    let mut keys: Vec<Bound<'py, PyAny>> = Vec::new();
    for reference in required_refs.try_iter()? {
        keys.push(ref_key.call1((reference?,))?);
    }
    for source_file in discovered.getattr("source_files")?.try_iter()? {
        for source in source_file?.getattr("source_entries")?.try_iter()? {
            let source: Bound<'py, PyAny> = source?;
            if loaders.contains(source.getattr("loader")?)? {
                keys.push(call_with(
                    &key_class,
                    &[
                        ("resource_type", source_type.clone()),
                        ("name", source.getattr("name")?),
                    ],
                )?);
            }
        }
    }
    let keys: Bound<'py, PyAny> = PyFrozenSet::new(py, keys)?.into_any();
    let resolver: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            EXTERNAL_REFS_MODULE,
            "resolve_external_sql_reference_resolver",
        )?,
        &[
            ("project_dir", invocation.getattr("effective_project_dir")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let options: Bound<'py, PyAny> = call_with(
        &imported(py, PIPELINE_MODELS, "CompilePipelineOptions")?,
        &[
            ("selected_target", request.getattr("selected_target")?),
            ("no_sql_validation", request.getattr("no_sql_validation")?),
            (
                "connection_config",
                invocation.getattr("connection_config")?,
            ),
            ("cli_vars", request.getattr("cli_vars")?),
            ("external_sql_reference_resolver", resolver),
        ],
    )?;
    let context: Bound<'py, PyAny> = call_with(
        &imported(py, STATIC_COMMAND_MODULE, "compile_static_command_context")?,
        &[
            ("discovered_inputs", discovered),
            ("adapter", invocation.getattr("adapter")?),
            ("options", options),
            ("selected_keys", keys.clone()),
            ("relation_keys", keys),
            (
                "on_progress",
                invocation
                    .getattr("planning_progress")?
                    .getattr("on_progress")?,
            ),
        ],
    )?;
    let plan_output: Bound<'py, PyAny> = call_with(
        &imported(py, RELATION_PLAN_MODULE, "build_relation_command_plan")?,
        &[
            ("project", context.getattr("project")?),
            ("scope", context.getattr("scope")?),
            ("relations", context.getattr("relations")?),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "build_static_pipeline_result")?,
        &[("context", context), ("plan_output", plan_output)],
    )
}

fn target_default<'py>(
    project: &Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    (field, fallback): (&str, &str),
) -> PyResult<Bound<'py, PyAny>> {
    let value: Bound<'py, PyAny> = project.getattr(field)?;
    if value.is_none() {
        adapter.call_method0(fallback)
    } else {
        Ok(value)
    }
}

/// The discovered Python graph, after refusing unit-test selectors, and the selected checks.
fn python_selection<'py>(
    request: &Bound<'py, PyAny>,
    discovered: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyFrozenSet>)> {
    let py: Python<'py> = request.py();
    let python_graph: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            PYTHON_GRAPH_MODULE,
            "build_discovered_python_node_graph",
        )?,
        &[("discovered_inputs", discovered.clone())],
    )?;
    call_with(
        &imported(py, REJECT_UNIT_TESTS_MODULE, "reject_unit_test_selectors")?,
        &[
            ("select", request.getattr("select")?),
            ("exclude", request.getattr("exclude")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let check_names: Bound<'py, PyFrozenSet> = selected_check_names(request, &python_graph)?;
    Ok((python_graph, check_names))
}

fn prepare<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Bound<'py, PyAny>,
) -> PyResult<Prepared<'py>> {
    let py: Python<'py> = request.py();
    let discovered: Bound<'py, PyAny> = invocation.getattr("discovered_inputs")?;
    let adapter: Bound<'py, PyAny> = invocation.getattr("adapter")?;
    let (planning_graph, planning_names) = python_selection(request, &discovered)?;
    let pipeline: Bound<'py, PyAny> =
        compile_pipeline(request, invocation, (&planning_graph, &planning_names))?;
    let (python_graph, check_names) = python_selection(request, &discovered)?;
    let mut check_functions: Vec<Bound<'py, PyAny>> = Vec::new();
    for check in discovered.getattr("check_functions")?.try_iter()? {
        let check: Bound<'py, PyAny> = check?;
        if check_names.contains(check.getattr("name")?)? {
            check_functions.push(check);
        }
    }
    let selection: Bound<'py, PyAny> = call_with(
        &imported(py, PYTHON_NODE_MODELS, "PythonSqlRunSelection")?,
        &[
            ("sql_keys", PyFrozenSet::empty(py)?.into_any()),
            ("python_node_names", PyFrozenSet::empty(py)?.into_any()),
        ],
    )?;
    let lifecycle_plan: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "build_python_sql_run_lifecycle")?,
        &[
            ("selection", selection),
            ("python_graph", python_graph.clone()),
        ],
    )?;
    let relation_refs: Bound<'py, PyAny> = call_with(
        &python_graph.getattr("selected_sql_refs")?,
        &[("selected_names", check_names.clone().into_any())],
    )?;
    let project: Bound<'py, PyAny> = pipeline.getattr("project")?;
    let plan_output: Bound<'py, PyAny> = pipeline.getattr("plan_output")?;
    let relation_targets: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "build_python_relation_targets")?,
        &[
            ("adapter", adapter.clone()),
            ("project", project.clone()),
            ("plan_output", plan_output.clone()),
            ("required_refs", relation_refs.clone()),
        ],
    )?;
    Ok(Prepared {
        check_functions: PyTuple::new(py, check_functions)?.into_any(),
        lifecycle_plan,
        relation_targets,
        relation_refs,
        defaults: (
            target_default(
                &project,
                &adapter,
                ("effective_target_database", "default_database"),
            )?,
            target_default(
                &project,
                &adapter,
                ("effective_target_schema", "default_schema"),
            )?,
        ),
        project_relations: call_with(
            &imported(py, NATIVE_MODULE, "build_project_relation_targets")?,
            &[("adapter", adapter), ("plan_output", plan_output)],
        )?,
        python_graph,
        pipeline,
    })
}

/// The executor runtime of check dependencies and checks; ingress runs without project relations.
fn node_runtime<'py>(
    invocation: &Bound<'py, PyAny>,
    prepared: &Prepared<'py>,
    (connection, providers, with_project_relations): (&Bound<'py, PyAny>, &Bound<'py, PyAny>, bool),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = invocation.py();
    let project: Bound<'py, PyAny> = prepared.pipeline.getattr("project")?;
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("adapter", invocation.getattr("adapter")?),
        (
            "connection_config",
            invocation.getattr("connection_config")?,
        ),
        ("connection", connection.clone()),
        ("run_id", project.getattr("run_id")?),
        ("target", project.getattr("effective_target_name")?),
        ("vars", project.getattr("effective_vars")?),
        ("is_reload", PyBool::new(py, false).to_owned().into_any()),
        ("default_database", prepared.defaults.0.clone()),
        ("default_schema", prepared.defaults.1.clone()),
        ("relation_targets", prepared.relation_targets.clone()),
    ];
    if with_project_relations {
        fields.push(("project_relations", prepared.project_relations.clone()));
    }
    fields.push(("providers", providers.clone()));
    call_with(
        &imported(py, EXECUTOR_MODELS, "PythonNodeRuntime")?,
        &fields,
    )
}

fn record_run_state<'py>(
    invocation: &Bound<'py, PyAny>,
    (run_state, python_results, load_results): (
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
        Option<Bound<'py, PyAny>>,
    ),
    source_map: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let py: Python<'py> = invocation.py();
    let mut fields: Vec<(&str, Bound<'py, PyAny>)> = vec![
        (
            "discovered_inputs",
            invocation.getattr("discovered_inputs")?,
        ),
        ("run_state", run_state),
        ("python_results", python_results),
    ];
    if let Some(load_results) = load_results {
        fields.push(("load_results", load_results));
    }
    fields.push(("source_map", source_map.clone()));
    call_with(
        &imported(py, CHECK_CORE_MODULE, "record_python_run_state_results")?,
        &fields,
    )?;
    Ok(())
}

/// Run ingress loaders and read-side dependencies, then the checks themselves.
fn run_checks<'py>(
    invocation: &Bound<'py, PyAny>,
    prepared: &Prepared<'py>,
    (connection, providers, event_writer): (
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
        &Bound<'py, PyAny>,
    ),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = invocation.py();
    let plan_output: Bound<'py, PyAny> = prepared.pipeline.getattr("plan_output")?;
    let source_map: Bound<'py, PyAny> = plan_output.getattr("source_map")?;
    let callbacks: Bound<'py, PyAny> = call_with(
        &imported(py, EXECUTOR_MODELS, "IngressCallbacks")?,
        &[("use_color", invocation.getattr("use_color")?)],
    )?;
    let ingress: Bound<'py, PyAny> = call_with(
        &imported(py, INGRESS_MODULE, "execute_ingress_python_loader_nodes")?,
        &[
            ("python_graph", prepared.python_graph.clone()),
            (
                "selected_python_names",
                prepared
                    .lifecycle_plan
                    .getattr("ingress_python_node_names")?,
            ),
            (
                "loader_functions",
                invocation
                    .getattr("discovered_inputs")?
                    .getattr("loader_functions")?,
            ),
            ("source_map", source_map.clone()),
            (
                "runtime",
                node_runtime(invocation, prepared, (connection, providers, false))?,
            ),
            ("callbacks", callbacks),
        ],
    )?;
    let run_state: Bound<'py, PyAny> = ingress.getattr("run_state")?;
    let load_results: Bound<'py, PyAny> = ingress.getattr("load_results")?;
    let ingress_python: Bound<'py, PyAny> = ingress.getattr("python_results")?;
    record_run_state(
        invocation,
        (
            run_state.clone(),
            ingress_python.clone(),
            Some(load_results.clone()),
        ),
        &source_map,
    )?;
    let read_side: Bound<'py, PyAny> = call_with(
        &imported(py, CHECK_CORE_MODULE, "run_check_read_side_dependencies")?,
        &[
            ("adapter", invocation.getattr("adapter")?),
            (
                "connection_config",
                invocation.getattr("connection_config")?,
            ),
            ("connection", connection.clone()),
            ("pipeline_result", prepared.pipeline.clone()),
            ("python_graph", prepared.python_graph.clone()),
            ("lifecycle_plan", prepared.lifecycle_plan.clone()),
            ("relation_targets", prepared.relation_targets.clone()),
            ("validation_refs", prepared.relation_refs.clone()),
            ("project_relations", prepared.project_relations.clone()),
            ("providers", providers.clone()),
        ],
    )?;
    record_run_state(
        invocation,
        (run_state.clone(), read_side.clone(), None),
        &source_map,
    )?;
    let upstream: Vec<Bound<'py, PyAny>> = ingress_python
        .try_iter()?
        .chain(read_side.try_iter()?)
        .collect::<PyResult<_>>()?;
    let by_loader: Bound<'py, PyAny> = call_with(
        &imported(py, CHECK_CORE_MODULE, "load_results_by_loader_name")?,
        &[
            ("source_map", source_map),
            ("load_results", load_results.clone()),
        ],
    )?;
    let on_complete: Bound<'py, PyAny> = Bound::new(
        py,
        CheckCompletionRelay {
            event_writer: event_writer.clone().unbind(),
            plan_output: plan_output.clone().unbind(),
        },
    )?
    .into_any();
    let check_callbacks: Bound<'py, PyAny> = call_with(
        &imported(py, EXECUTOR_MODELS, "PythonCheckCallbacks")?,
        &[("on_check_complete", on_complete)],
    )?;
    call_with(
        &imported(py, CHECKS_MODULE, "execute_python_checks")?,
        &[
            ("check_functions", prepared.check_functions.clone()),
            ("python_graph", prepared.python_graph.clone()),
            (
                "upstream_python_results",
                PyTuple::new(py, upstream)?.into_any(),
            ),
            ("upstream_load_results", load_results),
            ("upstream_load_results_by_loader_name", by_loader),
            (
                "runtime",
                node_runtime(invocation, prepared, (connection, providers, true))?,
            ),
            ("run_state", run_state),
            (
                "require_upstream_results",
                PyBool::new(py, false).to_owned().into_any(),
            ),
            ("callbacks", check_callbacks),
        ],
    )
}

/// Record each finished check in the event output.
#[pyclass(module = "sqlbuild._native", frozen)]
struct CheckCompletionRelay {
    event_writer: Py<PyAny>,
    plan_output: Py<PyAny>,
}

#[pymethods]
impl CheckCompletionRelay {
    fn __call__(&self, py: Python<'_>, result: &Bound<'_, PyAny>) -> PyResult<()> {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("result", result)?;
        options.set_item("plan", self.plan_output.bind(py))?;
        options.set_item("command", "check")?;
        self.event_writer
            .bind(py)
            .call_method("write_build_result", (), Some(&options))?;
        Ok(())
    }
}

/// Connect, configure progress ordinals, run the checks, and close everything.
fn execute<'py>(
    invocation: &Bound<'py, PyAny>,
    prepared: &Prepared<'py>,
    providers: &Bound<'py, PyAny>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = invocation.py();
    let adapter: Bound<'py, PyAny> = invocation.getattr("adapter")?;
    let connection: Bound<'py, PyAny> =
        adapter.call_method1("connect", (invocation.getattr("connection_config")?,))?;
    let event_writer: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "ExecutionEventWriter")?.call0()?;
    let executed: PyResult<Vec<Bound<'py, PyAny>>> = (|| {
        let projector: Bound<'py, PyAny> =
            imported(py, NATIVE_MODULE, "current_native_progress_projector")?.call0()?;
        if !projector.is_none() {
            let ordinals: Bound<'py, PyDict> = PyDict::new(py);
            let mut total: usize = 0;
            for check in prepared.check_functions.try_iter()? {
                total += 1;
                ordinals.set_item(check?.getattr("name")?, total)?;
            }
            let options: Bound<'py, PyDict> = PyDict::new(py);
            options.set_item("ordinals", ordinals)?;
            options.set_item("total", total)?;
            projector.call_method("configure_resources", (), Some(&options))?;
        }
        run_checks(
            invocation,
            prepared,
            (&connection, providers, &event_writer),
        )?
        .try_iter()?
        .collect()
    })();
    let writer_closed: PyResult<Bound<'py, PyAny>> = event_writer.call_method0("close");
    let connection_closed: PyResult<Bound<'py, PyAny>> =
        adapter.call_method1("close", (&connection,));
    let results: Vec<Bound<'py, PyAny>> = executed?;
    writer_closed?;
    connection_closed?;
    Ok(results)
}

/// Write rows, the summary, the runtime artifact and JSON output; returns the exit code.
fn complete<'py>(
    request: &Bound<'py, PyAny>,
    invocation: &Bound<'py, PyAny>,
    (prepared, results): (&Prepared<'py>, &[Bound<'py, PyAny>]),
) -> PyResult<i32> {
    let py: Python<'py> = request.py();
    let stream: Bound<'py, PyAny> = invocation.getattr("progress_stream")?;
    let style: CliStyle = CliStyle {
        use_color: invocation.getattr("use_color")?.extract()?,
    };
    write_results(
        &stream,
        results,
        (&prepared.check_functions, &prepared.python_graph),
        style,
    )?;
    let texts: Vec<CheckResultText> = results
        .iter()
        .map(check_result_text)
        .collect::<PyResult<_>>()?;
    stream.call_method1("write", (render_check_summary(&texts, style),))?;
    stream.call_method0("flush")?;
    let tuple: Bound<'py, PyAny> = PyTuple::new(py, results)?.into_any();
    call_with(
        &imported(
            py,
            RUNTIME_TARGET_MODULE,
            "write_python_check_runtime_target",
        )?,
        &[
            (
                "target_dir",
                invocation
                    .getattr("effective_project_dir")?
                    .call_method1("__truediv__", ("target",))?,
            ),
            ("results", tuple),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "write_execution_json_output")?,
        &[
            (
                "payload",
                PyString::new(py, &results_json(results)?).into_any(),
            ),
            ("json_output", request.getattr("json_output")?),
            ("json_output_path", request.getattr("json_output_path")?),
        ],
    )?;
    Ok(check_exit_code(&texts))
}

/// Run one `sqb check` request.
#[pyfunction]
#[pyo3(signature = (*, request))]
fn run_check_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let invocation: Bound<'_, PyAny> = call_with(
        &imported(py, INVOCATION_MODULE, "resolve_reported_command_invocation")?,
        &[
            ("request", request.clone()),
            (
                "invocation_type",
                imported(py, COMMAND_MODELS, "CheckInvocation")?,
            ),
        ],
    )?;
    let stream: Bound<'_, PyAny> = invocation.getattr("progress_stream")?;
    stream.call_method1("write", ("\n",))?;
    let header: Bound<'_, PyDict> = PyDict::new(py);
    header.set_item("stream", &stream)?;
    header.set_item("command", EXECUTION_COMMAND)?;
    header.set_item("target", py.None())?;
    header.set_item("concurrency", PyInt::new(py, 1))?;
    header.set_item("use_color", invocation.getattr("use_color")?)?;
    imported(py, NATIVE_MODULE, "write_execution_header")?.call((), Some(&header))?;
    let prepared: Prepared<'_> = prepare(request, &invocation)?;
    let session: Bound<'_, PyAny> = call_with(
        &imported(py, PROVIDER_SESSION_MODULE, "build_provider_session")?,
        &[(
            "discovered_providers",
            invocation
                .getattr("discovered_inputs")?
                .getattr("providers")?,
        )],
    )?;
    let outcome: PyResult<i32> = (|| {
        let results: Vec<Bound<'_, PyAny>> =
            execute(&invocation, &prepared, &session.getattr("providers")?)?;
        complete(request, &invocation, (&prepared, &results))
    })();
    let closed: PyResult<Bound<'_, PyAny>> = session.call_method0("close");
    let code: i32 = outcome?;
    closed?;
    Ok(code)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_check_command, module)?)?;
    Ok(())
}
