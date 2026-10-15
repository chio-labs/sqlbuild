//! Plan a compiled project over an open warehouse connection, and open that connection.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::phases::monotonic;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};

const NATIVE_MODULE: &str = "sqlbuild._native";
const EXECUTION_PLAN_MODULE: &str = "sqlbuild._native";
const PLANNER_MODELS_MODULE: &str = "sqlbuild.compiler.planner.models";
const MATERIALIZATIONS_MODULE: &str = "sqlbuild.compiler.pipeline._helpers.materializations";
const RUN_SELECTION_MODULE: &str = "sqlbuild.compiler.python_nodes.main._run_selection";
const PIPELINE_MODELS_MODULE: &str = "sqlbuild.compiler.pipeline.models";
const SINGLE_CONNECTION: i64 = 1;

/// The deferred relation locations and the warehouse relations behind them, when deferring.
type Deferral<'py> = (Bound<'py, PyAny>, Bound<'py, PyAny>);

/// The planning inputs: the discovered project, the adapter and its open connection.
pub(crate) struct PlanningInputs<'a, 'py> {
    pub(crate) discovered_inputs: &'a Bound<'py, PyAny>,
    pub(crate) adapter: &'a Bound<'py, PyAny>,
    pub(crate) connection: &'a Bound<'py, PyAny>,
}

/// Plan the compiled project over an open connection and attach Python node plans.
pub(crate) fn pipeline_result<'py>(
    inputs: &PlanningInputs<'_, 'py>,
    project: &Bound<'py, PyAny>,
    options: &Bound<'py, PyAny>,
    on_progress: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let native = py.import(NATIVE_MODULE)?;
    let discovered: &Bound<'py, PyAny> = inputs.discovered_inputs;
    let select: Bound<'py, PyAny> = options.getattr("select")?;
    let exclude: Bound<'py, PyAny> = options.getattr("exclude")?;
    let (deferred_locations, deferred_relations): Deferral<'py> =
        deferral(inputs, project, &options.getattr("defer_to")?)?;
    let empty = || -> PyResult<Bound<'py, PyAny>> { Ok(PyFrozenSet::empty(py)?.into_any()) };
    let mut selected_sql_keys: Bound<'py, PyAny> = py.None().into_bound(py);
    let mut selected_python_node_names: Bound<'py, PyAny> = empty()?;
    let mut python_read_source_names: Bound<'py, PyAny> = empty()?;
    let mut run_selection: Bound<'py, PyAny> = py.None().into_bound(py);
    let sql_test_selection: Bound<'py, PyAny> = options.getattr("sql_test_selection")?;
    if !sql_test_selection.getattr("models_selected")?.is_truthy()? {
        selected_sql_keys = empty()?;
    } else if options
        .getattr("resolve_python_run_selectors")?
        .is_truthy()?
    {
        let graph: Bound<'py, PyAny> = call_with(
            &native.getattr("build_project_graph_from_compiled_project")?,
            &[("project", project.clone())],
        )?;
        run_selection = call_with(
            &imported(
                py,
                RUN_SELECTION_MODULE,
                "resolve_python_sql_run_selection_from_inputs",
            )?,
            &[
                ("select", select.clone()),
                ("exclude", exclude.clone()),
                ("project_graph", graph),
                ("discovered_inputs", discovered.clone()),
            ],
        )?;
        selected_sql_keys = run_selection.getattr("sql_keys")?;
        selected_python_node_names = run_selection.getattr("python_node_names")?;
        python_read_source_names = call_with(
            &native.getattr("python_read_source_names_for")?,
            &[
                ("discovered_inputs", discovered.clone()),
                ("python_node_names", selected_python_node_names.clone()),
            ],
        )?;
    }
    let planner_models = py.import(PLANNER_MODELS_MODULE)?;
    let selection: Bound<'py, PyAny> = call_with(
        &planner_models.getattr("PlannerSelection")?,
        &[
            ("select", select),
            ("exclude", exclude),
            ("selected_keys", selected_sql_keys),
            ("python_read_source_names", python_read_source_names),
            ("sql_test_selection", sql_test_selection),
        ],
    )?;
    let overrides: Bound<'py, PyAny> = call_with(
        &planner_models.getattr("PlannerOverrides")?,
        &option_fields(
            options,
            &[
                "cursor_overrides",
                "full_refresh",
                "reload_sources",
                "max_microbatches",
            ],
        )?,
    )?;
    let mut deferral_fields: Vec<(&str, Bound<'py, PyAny>)> = vec![
        ("deferred_locations", deferred_locations),
        ("deferred_relations", deferred_relations),
    ];
    deferral_fields.extend(option_fields(
        options,
        &["defer_sources_to", "source_deferral_enabled"],
    )?);
    let deferral: Bound<'py, PyAny> =
        call_with(&planner_models.getattr("DeferralInputs")?, &deferral_fields)?;
    let policies: Bound<'py, PyAny> = call_with(
        &planner_models.getattr("PlannerPolicies")?,
        &option_fields(
            options,
            &[
                "auto_load_sources",
                "selection_diagnostics",
                "plan_sql_tests",
                "record_migration_fingerprints",
            ],
        )?,
    )?;
    let plan_output: Bound<'py, PyAny> = call_with(
        &imported(py, EXECUTION_PLAN_MODULE, "build_execution_plan")?,
        &[
            ("project", project.clone()),
            ("adapter", inputs.adapter.clone()),
            ("connection", inputs.connection.clone()),
            ("selection", selection),
            ("overrides", overrides),
            ("deferral", deferral),
            ("policies", policies),
            ("on_progress", on_progress.clone()),
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let custom_materializations: Bound<'py, PyAny> =
        imported(py, MATERIALIZATIONS_MODULE, "load_custom_materializations")?
            .call1((discovered.getattr("materialization_files")?,))?;
    let python_outputs: Bound<'py, PyAny> = call_with(
        &native.getattr("build_python_run_plan_outputs")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("plan_output", plan_output),
            ("run_selection", run_selection),
            ("selected_python_node_names", selected_python_node_names),
        ],
    )?;
    call_with(
        &imported(py, PIPELINE_MODELS_MODULE, "CompilePipelineResult")?,
        &[
            ("project", project.clone()),
            ("plan_output", python_outputs.getattr("plan_output")?),
            ("custom_materializations", custom_materializations),
            (
                "python_node_names",
                python_outputs.getattr("selected_python_node_names")?,
            ),
            (
                "python_plan_entries",
                python_outputs.getattr("python_plan_entries")?,
            ),
        ],
    )
}

/// `(name, options.name)` for each of `names`.
fn option_fields<'a, 'py>(
    options: &Bound<'py, PyAny>,
    names: &[&'a str],
) -> PyResult<Vec<(&'a str, Bound<'py, PyAny>)>> {
    names
        .iter()
        .map(|name| Ok((*name, options.getattr(*name)?)))
        .collect()
}

/// The deferred locations and relations of `defer_to`, or two `None`s when not deferring.
fn deferral<'py>(
    inputs: &PlanningInputs<'_, 'py>,
    project: &Bound<'py, PyAny>,
    defer_to: &Bound<'py, PyAny>,
) -> PyResult<Deferral<'py>> {
    let py: Python<'py> = project.py();
    if defer_to.is_none() {
        return Ok((py.None().into_bound(py), py.None().into_bound(py)));
    }
    let native = py.import(NATIVE_MODULE)?;
    let adapter: &Bound<'py, PyAny> = inputs.adapter;
    let target_config: Bound<'py, PyAny> = call_with(
        &native.getattr("resolve_deferred_target_config")?,
        &[
            ("discovered_inputs", inputs.discovered_inputs.clone()),
            ("defer_to", defer_to.clone()),
            (
                "current_target_name",
                project.getattr("effective_target_name")?,
            ),
        ],
    )?;
    let locations: Bound<'py, PyAny> = call_with(
        &native.getattr("build_deferred_locations")?,
        &[
            ("project", project.clone()),
            ("deferred_target_config", target_config),
            ("effective_vars", project.getattr("effective_vars")?),
            ("default_schema", adapter.call_method0("default_schema")?),
            (
                "default_database",
                adapter.call_method0("default_database")?,
            ),
            (
                "render_qualified_name",
                adapter.getattr("render_qualified_name")?,
            ),
        ],
    )?;
    let relations: Bound<'py, PyAny> = call_with(
        &native.getattr("gather_deferred_relations")?,
        &[
            ("adapter", adapter.clone()),
            ("connection", inputs.connection.clone()),
            ("deferred_locations", locations.clone()),
        ],
    )?;
    Ok((locations, relations))
}

/// Open one adapter connection and report its lifecycle through `hooks`.
pub(crate) fn connection_with_hooks<'py>(
    adapter: &Bound<'py, PyAny>,
    connection_config: &Bound<'py, PyAny>,
    hooks: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = adapter.py();
    let on_start: Bound<'py, PyAny> = hooks.getattr("on_connection_start")?;
    if !on_start.is_none() {
        on_start.call1((SINGLE_CONNECTION,))?;
    }
    let started: f64 = monotonic(py)?;
    let elapsed = |started: f64| -> PyResult<Bound<'py, PyDict>> {
        let keywords: Bound<'py, PyDict> = PyDict::new(py);
        keywords.set_item("elapsed_seconds", monotonic(py)? - started)?;
        Ok(keywords)
    };
    let connection: Bound<'py, PyAny> = match adapter.call_method1("connect", (connection_config,))
    {
        Ok(connection) => connection,
        Err(error) => {
            let on_error: Bound<'py, PyAny> = hooks.getattr("on_connection_error")?;
            if !on_error.is_none() {
                on_error.call((SINGLE_CONNECTION,), Some(&elapsed(started)?))?;
            }
            return Err(error);
        }
    };
    let on_complete: Bound<'py, PyAny> = hooks.getattr("on_connection_complete")?;
    if !on_complete.is_none() {
        on_complete.call((SINGLE_CONNECTION,), Some(&elapsed(started)?))?;
    }
    Ok(connection)
}

/// Open one adapter connection and report its lifecycle through hooks.
#[pyfunction]
#[pyo3(signature = (**options))]
fn open_connection_with_hooks<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "open_connection_with_hooks",
        options,
        (&["adapter", "connection_config", "hooks"], &[]),
    )?;
    connection_with_hooks(
        &arguments.value("adapter")?,
        &arguments.value("connection_config")?,
        &arguments.value("hooks")?,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(open_connection_with_hooks, module)?)
}
