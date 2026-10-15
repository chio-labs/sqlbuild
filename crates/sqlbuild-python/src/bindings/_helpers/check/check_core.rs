//! Python check planning: run-state recording, dependency relations and read-side preflight.

use pyo3::IntoPyObject;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyFrozenSetMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use sqlbuild_core::build_command::errors::BuildCommandError;

use crate::bindings::_helpers::build_command::policies::build_command_error;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const BUILD_TYPES: &str = "sqlbuild.executor.build.types";
const PYTHON_NODE_TYPES: &str = "sqlbuild.compiler.python_nodes.types";
const EXECUTOR_MODELS: &str = "sqlbuild.executor.python_nodes.models";
const READ_SIDE_MODULE: &str = "sqlbuild.executor.python_nodes.main.read_side";
const RELATION_LOOKUP_MODULE: &str = "sqlbuild.adapter.relations.main.relation_lookup";
const QUALIFIED_NAME_MODULE: &str =
    "sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name";
const MISSING_RELATION_CODE: &str = "C682";
const MODEL_KIND: &str = "model";
const SEED_KIND: &str = "seed";
const SOURCE_KIND: &str = "source";
const READ_SIDE_OPTIONS: (&[&str], &[&str]) = (
    &[
        "adapter",
        "connection_config",
        "connection",
        "pipeline_result",
        "python_graph",
        "lifecycle_plan",
        "relation_targets",
    ],
    &["validation_refs", "project_relations", "providers"],
);

fn user_error(py: Python<'_>, message: String) -> PyErr {
    build_command_error(
        py,
        BuildCommandError {
            code: Some(MISSING_RELATION_CODE.to_owned()),
            message,
            help: None,
        },
    )
}

/// The loader node result a load result stands for.
fn load_result_as_python_result<'py>(
    name: &Bound<'py, PyAny>,
    result: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = name.py();
    let execution: Bound<'py, PyAny> = imported(py, BUILD_TYPES, "ExecutionStatus")?;
    let node_status: Bound<'py, PyAny> = imported(py, PYTHON_NODE_TYPES, "PythonNodeStatus")?;
    let status: Bound<'py, PyAny> = result.getattr("status")?;
    let mapped: Bound<'py, PyAny> = if status.eq(execution.getattr("SUCCESS")?)? {
        node_status.getattr("SUCCESS")?
    } else if status.eq(execution.getattr("SKIPPED")?)? {
        node_status.getattr("SKIPPED")?
    } else {
        node_status.getattr("FAILED")?
    };
    call_with(
        &imported(py, EXECUTOR_MODELS, "PythonNodeExecutionResult")?,
        &[
            ("node_name", name.clone()),
            (
                "kind",
                imported(py, PYTHON_NODE_TYPES, "PythonNodeKind")?.getattr("LOADER")?,
            ),
            ("status", mapped),
            ("payload", result.clone()),
            ("error_message", result.getattr("error_message")?),
        ],
    )
}

/// Load results keyed by loader name for check dependency lookup.
pub(crate) fn load_results_by_loader_name<'py>(
    source_map: &Bound<'py, PyAny>,
    load_results: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = source_map.py();
    let loader_by_source: Bound<'py, PyDict> = PyDict::new(py);
    for item in source_map.call_method0("items")?.try_iter()? {
        let (name, source): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        let loader: Bound<'py, PyAny> = source.getattr("loader")?;
        if !loader.is_none() {
            loader_by_source.set_item(name, loader)?;
        }
    }
    let by_loader: Bound<'py, PyDict> = PyDict::new(py);
    for result in load_results.try_iter()? {
        let result: Bound<'py, PyAny> = result?;
        if let Some(loader) = loader_by_source.get_item(result.getattr("source_name")?)?
            && !loader.is_none()
        {
            by_loader.set_item(loader, result)?;
        }
    }
    Ok(by_loader)
}

/// Record Python and loader results in the Python run-state.
pub(crate) fn record_python_run_state_results<'py>(
    discovered_inputs: &Bound<'py, PyAny>,
    run_state: &Bound<'py, PyAny>,
    (python_results, load_results): (&Bound<'py, PyAny>, Option<&Bound<'py, PyAny>>),
    source_map: Option<&Bound<'py, PyAny>>,
) -> PyResult<()> {
    let py: Python<'py> = discovered_inputs.py();
    let record = |function: Bound<'py, PyAny>, result: Bound<'py, PyAny>| -> PyResult<()> {
        call_with(
            &run_state.getattr("record_result")?,
            &[("node_function", function), ("result", result)],
        )?;
        Ok(())
    };
    let result_by_name: Bound<'py, PyDict> = PyDict::new(py);
    for result in python_results.try_iter()? {
        let result: Bound<'py, PyAny> = result?;
        result_by_name.set_item(result.getattr("node_name")?, result)?;
    }
    let node_by_name: Bound<'py, PyDict> = PyDict::new(py);
    for attribute in ["task_functions", "asset_functions"] {
        for node in discovered_inputs.getattr(attribute)?.try_iter()? {
            let node: Bound<'py, PyAny> = node?;
            node_by_name.set_item(node.getattr("name")?, node.getattr("function")?)?;
        }
    }
    for (name, function) in node_by_name.iter() {
        if let Some(result) = result_by_name.get_item(name)? {
            record(function, result)?;
        }
    }
    let by_loader: Bound<'py, PyDict> = match (source_map, load_results) {
        (Some(source_map), Some(load_results)) => {
            load_results_by_loader_name(source_map, load_results)?
        }
        (Some(source_map), None) => {
            load_results_by_loader_name(source_map, &PyTuple::empty(py).into_any())?
        }
        _ => PyDict::new(py),
    };
    for loader in discovered_inputs.getattr("loader_functions")?.try_iter()? {
        let loader: Bound<'py, PyAny> = loader?;
        let name: Bound<'py, PyAny> = loader.getattr("name")?;
        let Some(result) = by_loader.get_item(&name)? else {
            continue;
        };
        record(
            loader.getattr("function")?,
            load_result_as_python_result(&name, &result)?,
        )?;
    }
    Ok(())
}

/// SQL relation locations available to Python check dependencies.
pub(crate) fn build_check_relation_targets<'py>(
    adapter: &Bound<'py, PyAny>,
    pipeline_result: &Bound<'py, PyAny>,
    python_graph: &Bound<'py, PyAny>,
    selected_python_names: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = adapter.py();
    let required: Bound<'py, PyAny> = call_with(
        &python_graph.getattr("selected_sql_refs")?,
        &[("selected_names", selected_python_names)],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "build_python_relation_targets")?,
        &[
            ("adapter", adapter.clone()),
            ("project", pipeline_result.getattr("project")?),
            ("plan_output", pipeline_result.getattr("plan_output")?),
            ("required_refs", required),
        ],
    )
}

/// Non-excluded checks whose Python and SQL dependencies all ran in this build.
pub(crate) fn relevant_check_functions<'py>(
    discovered_inputs: &Bound<'py, PyAny>,
    python_graph: &Bound<'py, PyAny>,
    exclude: Bound<'py, PyAny>,
    (selected_dependency_names, completed_sql_names): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let py: Python<'py> = discovered_inputs.py();
    let excluded: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_python_check_excludes")?,
        &[("graph", python_graph.clone()), ("exclude", exclude)],
    )?;
    let check_kind: Bound<'py, PyAny> =
        imported(py, PYTHON_NODE_TYPES, "PythonNodeKind")?.getattr("CHECK")?;
    let upstream_deps: Bound<'py, PyAny> = python_graph.getattr("upstream_deps")?;
    let mut check_names: Vec<Bound<'py, PyAny>> = Vec::new();
    for node in python_graph.getattr("nodes")?.try_iter()? {
        let node: Bound<'py, PyAny> = node?;
        let name: Bound<'py, PyAny> = node.getattr("name")?;
        if !node.getattr("kind")?.eq(&check_kind)? || excluded.contains(&name)? {
            continue;
        }
        let upstream: Vec<Bound<'py, PyAny>> = upstream_deps
            .call_method1("get", (&name, PyTuple::empty(py)))?
            .try_iter()?
            .collect::<PyResult<_>>()?;
        let mut sql_names: Vec<Bound<'py, PyAny>> = Vec::new();
        for reference in node.getattr("sql_deps")?.try_iter()? {
            sql_names.push(reference?.getattr("name")?);
        }
        if upstream.is_empty() && sql_names.is_empty() {
            continue;
        }
        let mut ready: bool = true;
        for upstream_name in &upstream {
            ready = ready && selected_dependency_names.contains(upstream_name)?;
        }
        for sql_name in &sql_names {
            ready = ready && completed_sql_names.contains(sql_name)?;
        }
        if ready {
            check_names.push(name);
        }
    }
    let check_names: Bound<'py, PyFrozenSet> = PyFrozenSet::new(py, &check_names)?;
    let mut checks: Vec<Bound<'py, PyAny>> = Vec::new();
    for check in discovered_inputs.getattr("check_functions")?.try_iter()? {
        let check: Bound<'py, PyAny> = check?;
        if check_names.contains(check.getattr("name")?)? {
            checks.push(check);
        }
    }
    Ok(checks)
}

/// Inputs of the read-side preflight `sqb check` runs before the checks themselves.
pub(crate) struct ReadSideInputs<'py> {
    pub(crate) adapter: Bound<'py, PyAny>,
    pub(crate) connection_config: Bound<'py, PyAny>,
    pub(crate) connection: Bound<'py, PyAny>,
    pub(crate) pipeline_result: Bound<'py, PyAny>,
    pub(crate) python_graph: Bound<'py, PyAny>,
    pub(crate) lifecycle_plan: Bound<'py, PyAny>,
    pub(crate) relation_targets: Bound<'py, PyAny>,
    pub(crate) validation_refs: Bound<'py, PyAny>,
    pub(crate) project_relations: Bound<'py, PyAny>,
    pub(crate) providers: Bound<'py, PyAny>,
}

fn reference_kind(reference: &Bound<'_, PyAny>) -> PyResult<String> {
    reference.getattr("kind")?.getattr("value")?.extract()
}

/// A plan source the check can look up as a table: not an expression, with a table name.
fn table_source<'py>(
    plan_output: &Bound<'py, PyAny>,
    name: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let source: Bound<'py, PyAny> = plan_output
        .getattr("python_source_entries")?
        .call_method1("get", (name,))?;
    if source.is_none()
        || !source.getattr("expression")?.is_none()
        || source.getattr("table")?.is_none()
    {
        return Ok(None);
    }
    Ok(Some(source))
}

fn located<'py>(
    plan_output: &Bound<'py, PyAny>,
    reference: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let attribute: &str = match reference_kind(reference)?.as_str() {
        MODEL_KIND => "model_locations",
        SEED_KIND => "seed_locations",
        _ => return Ok(None),
    };
    let location: Bound<'py, PyAny> = plan_output
        .getattr(attribute)?
        .call_method1("get", (reference.getattr("name")?,))?;
    Ok((!location.is_none()).then_some(location))
}

/// `(database, schema, name)` of the relation a reference reads, when it has one.
fn lookup_location<'py>(
    plan_output: &Bound<'py, PyAny>,
    reference: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let py: Python<'py> = plan_output.py();
    let parts: (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>) =
        if reference_kind(reference)? == SOURCE_KIND {
            let Some(source) = table_source(plan_output, &reference.getattr("name")?)? else {
                return Ok(None);
            };
            (
                source.getattr("database")?,
                source.getattr("schema")?,
                source.getattr("table")?,
            )
        } else {
            let Some(location) = located(plan_output, reference)? else {
                return Ok(None);
            };
            (
                location.getattr("database")?,
                location.getattr("schema")?,
                location.getattr("name")?,
            )
        };
    Ok(Some(
        PyTuple::new(py, [parts.0, parts.1, parts.2])?.into_any(),
    ))
}

fn relation_exists(
    lookup: &Bound<'_, PyAny>,
    (database, schema, name): (Bound<'_, PyAny>, Bound<'_, PyAny>, Bound<'_, PyAny>),
) -> PyResult<bool> {
    call_with(
        &lookup.getattr("exists")?,
        &[("database", database), ("schema", schema), ("name", name)],
    )?
    .is_truthy()
}

/// Reject a check SQL dependency whose relation does not exist yet.
fn validate_reference_exists(
    inputs: &ReadSideInputs<'_>,
    lookup: &Bound<'_, PyAny>,
    reference: &Bound<'_, PyAny>,
) -> Result<(), PyErr> {
    let py: Python<'_> = reference.py();
    let plan_output: Bound<'_, PyAny> = inputs.pipeline_result.getattr("plan_output")?;
    let kind: String = reference_kind(reference)?;
    let name: Bound<'_, PyAny> = reference.getattr("name")?;
    let (exists, relation): (bool, Bound<'_, PyAny>) = match kind.as_str() {
        MODEL_KIND | SEED_KIND => {
            let Some(location) = located(&plan_output, reference)? else {
                let noun: &str = if kind == MODEL_KIND {
                    "SQL model"
                } else {
                    "seed"
                };
                return Err(user_error(
                    py,
                    format!(
                        "Python check dependency requires unknown {noun} '{}'",
                        name.str()?
                    ),
                ));
            };
            let exists: bool = relation_exists(
                lookup,
                (
                    location.getattr("database")?,
                    location.getattr("schema")?,
                    location.getattr("name")?,
                ),
            )?;
            let relation: Bound<'_, PyAny> = call_with(
                &imported(
                    py,
                    QUALIFIED_NAME_MODULE,
                    "resolve_relation_location_qualified_name",
                )?,
                &[("adapter", inputs.adapter.clone()), ("location", location)],
            )?;
            (exists, relation)
        }
        SOURCE_KIND => {
            let Some(source) = table_source(&plan_output, &name)? else {
                return Ok(());
            };
            let exists: bool = relation_exists(
                lookup,
                (
                    source.getattr("database")?,
                    source.getattr("schema")?,
                    source.getattr("table")?,
                ),
            )?;
            (exists, inputs.relation_targets.get_item(reference)?)
        }
        _ => return Ok(()),
    };
    if exists {
        return Ok(());
    }
    Err(user_error(
        py,
        format!(
            "Python check dependency requires existing SQL relation '{}' for {kind} '{}'; run sqb build first",
            relation.str()?,
            name.str()?
        ),
    ))
}

fn sorted_references<'py>(references: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut keyed: Vec<((String, String), Bound<'py, PyAny>)> = Vec::new();
    for reference in references.try_iter()? {
        let reference: Bound<'py, PyAny> = reference?;
        let key: (String, String) = (
            reference_kind(&reference)?,
            reference.getattr("name")?.extract()?,
        );
        keyed.push((key, reference));
    }
    keyed.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(keyed.into_iter().map(|(_, reference)| reference).collect())
}

fn read_side_references<'py>(
    python_graph: &Bound<'py, PyAny>,
    read_side_names: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = python_graph.py();
    let nodes: Bound<'py, PyAny> = python_graph.getattr("nodes_by_name")?;
    let mut references: Vec<Bound<'py, PyAny>> = Vec::new();
    for name in read_side_names.try_iter()? {
        for reference in nodes.get_item(name?)?.getattr("sql_deps")?.try_iter()? {
            references.push(reference?);
        }
    }
    Ok(PyFrozenSet::new(py, &references)?.into_any())
}

fn node_runtime<'py>(inputs: &ReadSideInputs<'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.adapter.py();
    let project: Bound<'py, PyAny> = inputs.pipeline_result.getattr("project")?;
    call_with(
        &imported(py, EXECUTOR_MODELS, "PythonNodeRuntime")?,
        &[
            ("adapter", inputs.adapter.clone()),
            ("connection_config", inputs.connection_config.clone()),
            ("connection", inputs.connection.clone()),
            ("run_id", project.getattr("run_id")?),
            ("target", project.getattr("effective_target_name")?),
            ("vars", project.getattr("effective_vars")?),
            ("is_reload", false.into_pyobject(py)?.to_owned().into_any()),
            (
                "default_database",
                inputs.adapter.call_method0("default_database")?,
            ),
            (
                "default_schema",
                inputs.adapter.call_method0("default_schema")?,
            ),
            ("relation_targets", inputs.relation_targets.clone()),
            ("project_relations", inputs.project_relations.clone()),
            ("providers", inputs.providers.clone()),
        ],
    )
}

/// Run read-side Python dependencies for checks against existing SQL relations.
pub(crate) fn run_read_side_dependencies<'py>(
    inputs: &ReadSideInputs<'py>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.adapter.py();
    let read_side_names: Bound<'py, PyAny> = inputs
        .lifecycle_plan
        .getattr("read_side_python_node_names")?;
    let to_validate: Bound<'py, PyAny> = if inputs.validation_refs.is_none() {
        read_side_references(&inputs.python_graph, &read_side_names)?
    } else {
        inputs.validation_refs.clone()
    };
    let references: Vec<Bound<'py, PyAny>> = sorted_references(&to_validate)?;
    let plan_output: Bound<'py, PyAny> = inputs.pipeline_result.getattr("plan_output")?;
    let mut locations: Vec<Bound<'py, PyAny>> = Vec::new();
    for reference in &references {
        if let Some(location) = lookup_location(&plan_output, reference)? {
            locations.push(location);
        }
    }
    let lookup: Bound<'py, PyAny> = call_with(
        &imported(py, RELATION_LOOKUP_MODULE, "build_relation_lookup")?,
        &[
            ("adapter", inputs.adapter.clone()),
            ("connection", inputs.connection.clone()),
            ("locations", PyTuple::new(py, locations)?.into_any()),
        ],
    )?;
    for reference in &references {
        validate_reference_exists(inputs, &lookup, reference)?;
    }
    if !read_side_names.is_truthy()? {
        return Ok(PyTuple::empty(py).into_any());
    }
    let tracker: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            READ_SIDE_MODULE,
            "create_read_side_python_execution_tracker",
        )?,
        &[
            ("python_graph", inputs.python_graph.clone()),
            ("selected_python_names", read_side_names),
            ("scheduled_sql_names", PyFrozenSet::empty(py)?.into_any()),
            ("runtime", node_runtime(inputs)?),
        ],
    )?;
    tracker.call_method0("dispatch_ready_python_nodes")?;
    tracker.call_method0("finalize_unrun_python_nodes")?;
    tracker.getattr("results")
}

/// Run read-side Python dependencies for checks against existing SQL relations.
#[pyfunction]
#[pyo3(signature = (**options))]
fn run_check_read_side_dependencies<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "run_check_read_side_dependencies",
        options,
        READ_SIDE_OPTIONS,
    )?;
    run_read_side_dependencies(&ReadSideInputs {
        adapter: arguments.value("adapter")?,
        connection_config: arguments.value("connection_config")?,
        connection: arguments.value("connection")?,
        pipeline_result: arguments.value("pipeline_result")?,
        python_graph: arguments.value("python_graph")?,
        lifecycle_plan: arguments.value("lifecycle_plan")?,
        relation_targets: arguments.value("relation_targets")?,
        validation_refs: arguments.value("validation_refs")?,
        project_relations: arguments.value("project_relations")?,
        providers: arguments.value("providers")?,
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_check_read_side_dependencies, module)?)
}
