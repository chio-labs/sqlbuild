//! Compiled project and project graph construction: frontier stages, target defaults and checks.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyCFunction, PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::phases::monotonic;
use crate::bindings::_helpers::compile_driver::pipeline_entries::project_graph;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords, within,
};
use crate::bindings::_helpers::compile_driver::target_defaults::{
    TargetDefaults, apply_target_defaults,
};
use crate::bindings::_helpers::compile_driver::targets::{
    managed_loader_target_isolation, managed_write_schemas, named_target_schema_strategy,
    project_targets,
};

const FRONTIER_MODULE: &str = "sqlbuild._native";
const FRONTIER_TYPES_MODULE: &str = "sqlbuild.compiler.frontier.types";
const BUILD_INPUTS_MODULE: &str = "sqlbuild._native";
const ASSEMBLE_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const PROJECT_WITH_MODULE: &str = "sqlbuild._native";
const PROMOTION_MODULE: &str = "sqlbuild._native";
const DISCOVERY_CONSTANTS_MODULE: &str = "sqlbuild.compiler.discovery.constants";
const LINEAGE_TYPES_MODULE: &str = "sqlbuild.compiler.lineage.types";
const ANALYSIS_SELECTION_MODULE: &str = "sqlbuild.compiler.pipeline._helpers.analysis_selection";
const PROFILING_MODULE: &str = "sqlbuild.compiler.profiling.main._record";
const ADAPTER_NAME_MODULE: &str = "sqlbuild.spec.contracts.main.resolve_effective_adapter_name";
const COLLECTION_RENDERING_MODULE: &str =
    "sqlbuild.spec.contracts.main.resolve_effective_collection_rendering";
/// Optional keywords of the project graph builders.
const GRAPH_OPTIONAL: [&str; 7] = [
    "selected_target",
    "no_sql_validation",
    "skip_column_inference",
    "column_lineage_mode",
    "cli_vars",
    "external_sql_reference_resolver",
    "on_progress",
];

/// The keyword arguments of one compiled-project build.
struct ProjectRequest {
    discovered_inputs: Py<PyAny>,
    adapter: Py<PyAny>,
    selected_target: Py<PyAny>,
    no_sql_validation: bool,
    skip_column_inference: bool,
    column_lineage_mode: Py<PyAny>,
    cli_vars: Py<PyAny>,
    external_sql_reference_resolver: Py<PyAny>,
    resolved_connection: Py<PyAny>,
    analysis_selection: Py<PyAny>,
}

/// `column_lineage_mode`, defaulting to `ColumnLineageMode.FAST` when not passed.
pub(crate) fn lineage_mode<'py>(arguments: &KeywordArguments<'py>) -> PyResult<Bound<'py, PyAny>> {
    let mode: Bound<'py, PyAny> = arguments.value("column_lineage_mode")?;
    if arguments.passed("column_lineage_mode")? {
        return Ok(mode);
    }
    imported(mode.py(), LINEAGE_TYPES_MODULE, "ColumnLineageMode")?.getattr("FAST")
}

/// `value` as a Python `bool`.
fn py_bool(py: Python<'_>, value: bool) -> Bound<'_, PyAny> {
    PyBool::new(py, value).to_owned().into_any()
}

/// Build one compiled project with adapter defaults and target validation applied.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_compiled_project<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_compiled_project",
        options,
        (
            &["discovered_inputs", "adapter"],
            &[
                "selected_target",
                "no_sql_validation",
                "skip_column_inference",
                "column_lineage_mode",
                "cli_vars",
                "external_sql_reference_resolver",
                "resolved_connection",
                "analysis_selection",
            ],
        ),
    )?;
    compiled_project(py, ProjectRequest::read(&arguments)?)
}

impl ProjectRequest {
    /// The request named by keyword `arguments`.
    fn read(arguments: &KeywordArguments<'_>) -> PyResult<Self> {
        Ok(Self {
            discovered_inputs: arguments.value("discovered_inputs")?.unbind(),
            adapter: arguments.value("adapter")?.unbind(),
            selected_target: arguments.value("selected_target")?.unbind(),
            no_sql_validation: arguments.flag("no_sql_validation")?,
            skip_column_inference: arguments.flag("skip_column_inference")?,
            column_lineage_mode: lineage_mode(arguments)?.unbind(),
            cli_vars: arguments.value("cli_vars")?.unbind(),
            external_sql_reference_resolver: arguments
                .value("external_sql_reference_resolver")?
                .unbind(),
            resolved_connection: arguments.value("resolved_connection")?.unbind(),
            analysis_selection: arguments.value("analysis_selection")?.unbind(),
        })
    }
}

/// The compiled project produced through the `COMPILED_PROJECT` frontier.
fn compiled_project(py: Python<'_>, request: ProjectRequest) -> PyResult<Bound<'_, PyAny>> {
    let stage: Bound<'_, PyCFunction> = PyCFunction::new_closure(
        py,
        None,
        None,
        move |arguments: &Bound<'_, PyTuple>, _: Option<&Bound<'_, PyDict>>| {
            python_compiled_project(arguments.py(), &request).map(Bound::unbind)
        },
    )?;
    call_with(
        &imported(py, FRONTIER_MODULE, "compile_frontier")?,
        &[
            (
                "until",
                imported(py, FRONTIER_TYPES_MODULE, "CompilerStage")?
                    .getattr("COMPILED_PROJECT")?,
            ),
            ("python_stage", stage.into_any()),
        ],
    )
}

/// `_build_python_compiled_project`.
fn python_compiled_project<'py>(
    py: Python<'py>,
    request: &ProjectRequest,
) -> PyResult<Bound<'py, PyAny>> {
    let discovered: &Bound<'py, PyAny> = request.discovered_inputs.bind(py);
    let adapter: &Bound<'py, PyAny> = request.adapter.bind(py);
    named_target_schema_strategy(discovered, adapter, request.selected_target.bind(py))?;
    managed_loader_target_isolation(discovered, adapter, request.resolved_connection.bind(py))?;
    let selection: &Bound<'py, PyAny> = request.analysis_selection.bind(py);
    let no_cache: bool = !selection.is_none() && selection.getattr("no_cache")?.is_truthy()?;
    let timing: Bound<'py, PyAny> =
        imported(py, PROFILING_MODULE, "record_compile_timing")?.call1(("attachment_ms",))?;
    let compile_inputs: Bound<'py, PyAny> =
        within(&timing, |_| frontier_compile_inputs(py, request, no_cache))?;
    if !selection.is_none() {
        let on_inputs_ready: Bound<'py, PyAny> = selection.getattr("on_inputs_ready")?;
        if !on_inputs_ready.is_none() {
            call_with(&on_inputs_ready, &[("inputs", compile_inputs.clone())])?;
        }
    }
    let inference_profile: Bound<'py, PyAny> =
        adapter.call_method0("expression_inference_profile")?;
    let analysis_model_names: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            ANALYSIS_SELECTION_MODULE,
            "resolve_analysis_model_names",
        )?,
        &[
            ("compile_inputs", compile_inputs.clone()),
            ("inference_profile", inference_profile.clone()),
            ("selection", selection.clone()),
        ],
    )?;
    let project: Bound<'py, PyAny> = call_with(
        &imported(py, ASSEMBLE_MODULE, "assemble_project")?,
        &[
            ("inputs", compile_inputs.clone()),
            ("inference_profile", inference_profile),
            (
                "skip_column_inference",
                py_bool(py, request.skip_column_inference),
            ),
            (
                "column_lineage_mode",
                request.column_lineage_mode.bind(py).clone(),
            ),
            (
                "analysis_cache_dir",
                compile_inputs.getattr("compile_cache_dir")?,
            ),
            ("analysis_model_names", analysis_model_names),
        ],
    )?;
    targeted_project(py, request, &project)
}

/// The assembled project with target defaults, target checks and promotion conflicts applied.
fn targeted_project<'py>(
    py: Python<'py>,
    request: &ProjectRequest,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let discovered: &Bound<'py, PyAny> = request.discovered_inputs.bind(py);
    let adapter: &Bound<'py, PyAny> = request.adapter.bind(py);
    managed_write_schemas(adapter, project)?;
    let effective_schema: Bound<'py, PyAny> = project.getattr("effective_target_schema")?;
    let default_schema: Bound<'py, PyAny> = if effective_schema.is_truthy()? {
        effective_schema
    } else {
        adapter.call_method0("default_schema")?
    };
    let defaults: TargetDefaults<'py> = TargetDefaults {
        default_schema,
        default_database: adapter.call_method0("default_database")?,
        render_qualified_name: adapter.getattr("render_qualified_name")?,
        python_functions_inherit_default_namespace: adapter
            .call_method0("python_functions_inherit_default_namespace")?,
    };
    let project: Bound<'py, PyAny> = apply_target_defaults(project, &defaults)?;
    let project_config: Bound<'py, PyAny> = discovered.getattr("project_config")?;
    let local_config: Bound<'py, PyAny> = discovered.getattr("local_config")?;
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", project_config),
            ("local_config", local_config.clone()),
        ],
    )?;
    project_targets(&adapter_name, &project)?;
    let promotion_key: Bound<'py, PyAny> = imported(
        py,
        DISCOVERY_CONSTANTS_MODULE,
        "TABLE_PROMOTION_MODE_SETTING_KEY",
    )?;
    let settings_file: Bound<'py, PyAny> = imported(
        py,
        DISCOVERY_CONSTANTS_MODULE,
        if local_config
            .getattr("setting_overrides")?
            .contains(promotion_key)?
        {
            "LOCAL_CONFIG_FILENAME"
        } else {
            "PROJECT_CONFIG_FILENAME"
        },
    )?;
    let conflicts: Bound<'py, PyAny> = call_with(
        &imported(py, PROMOTION_MODULE, "promotion_conflict_diagnostics")?,
        &[
            ("project", project.clone()),
            (
                "adapter_default",
                adapter.call_method0("default_table_promotion_mode")?,
            ),
            ("settings_file", settings_file),
        ],
    )?;
    let diagnostics: Bound<'py, PyTuple> = PyTuple::new(
        py,
        project
            .getattr("diagnostics")?
            .try_iter()?
            .chain(conflicts.try_iter()?)
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    call_with(
        &imported(py, PROJECT_WITH_MODULE, "project_with")?,
        &[
            ("project", project),
            ("diagnostics", diagnostics.into_any()),
        ],
    )
}

/// The compile inputs produced through the `COMPILE_PROJECT_INPUTS` frontier.
fn frontier_compile_inputs<'py>(
    py: Python<'py>,
    request: &ProjectRequest,
    no_cache: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let discovered: &Bound<'py, PyAny> = request.discovered_inputs.bind(py);
    let adapter: &Bound<'py, PyAny> = request.adapter.bind(py);
    let collection_rendering: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            COLLECTION_RENDERING_MODULE,
            "resolve_effective_collection_rendering",
        )?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("declaration_override", py.None().into_bound(py)),
        ],
    )?;
    let adapter_context: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "CompileAdapterContext")?,
        &[
            ("value_renderer", adapter.clone()),
            ("collection_rendering", collection_rendering),
            (
                "python_functions_inherit_default_namespace",
                adapter.call_method0("python_functions_inherit_default_namespace")?,
            ),
            ("sql_lexical_syntax", adapter.getattr("sql_lexical_syntax")?),
        ],
    )?;
    let stage: Bound<'py, PyAny> = imported(py, "functools", "partial")?.call(
        (imported(py, BUILD_INPUTS_MODULE, "build_compile_inputs")?,),
        Some(&keywords(
            py,
            &[
                ("discovered_inputs", discovered.clone()),
                ("adapter_context", adapter_context),
                ("selected_target", request.selected_target.bind(py).clone()),
                ("no_sql_validation", py_bool(py, request.no_sql_validation)),
                ("defer_model_sql_validation", py_bool(py, true)),
                ("cli_vars", request.cli_vars.bind(py).clone()),
                (
                    "resolved_connection",
                    request.resolved_connection.bind(py).clone(),
                ),
                (
                    "external_sql_reference_resolver",
                    request.external_sql_reference_resolver.bind(py).clone(),
                ),
                ("no_cache", py_bool(py, no_cache)),
            ],
        )?),
    )?;
    call_with(
        &imported(py, FRONTIER_MODULE, "compile_frontier")?,
        &[
            (
                "until",
                imported(py, FRONTIER_TYPES_MODULE, "CompilerStage")?
                    .getattr("COMPILE_PROJECT_INPUTS")?,
            ),
            ("python_stage", stage),
        ],
    )
}

/// Build a static graph with an explicit deep-analysis selection.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_project_graph_with_analysis_selection<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_project_graph_with_analysis_selection",
        options,
        (
            &["discovered_inputs", "adapter", "analysis_selection"],
            &GRAPH_OPTIONAL,
        ),
    )?;
    selected_graph(&arguments, arguments.value("analysis_selection")?)
}

/// Build the static dependency graph for a compiled project.
#[pyfunction]
#[pyo3(signature = (**options))]
fn build_project_graph<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let mut optional: Vec<&str> = GRAPH_OPTIONAL.to_vec();
    optional.push("no_cache");
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_project_graph",
        options,
        (&["discovered_inputs", "adapter"], &optional),
    )?;
    let selection: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "CompileAnalysisSelection")?,
        &[("no_cache", py_bool(py, arguments.flag("no_cache")?))],
    )?;
    selected_graph(&arguments, selection)
}

/// `build_project_graph_with_analysis_selection` with its `analysis_selection`.
fn selected_graph<'py>(
    arguments: &KeywordArguments<'py>,
    analysis_selection: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let on_progress: Bound<'py, PyAny> = arguments.value("on_progress")?;
    let py: Python<'py> = on_progress.py();
    if !on_progress.is_none() {
        on_progress.call1(("Compiling project...",))?;
    }
    let started: f64 = monotonic(py)?;
    let mut request: ProjectRequest = ProjectRequest::read(arguments)?;
    request.analysis_selection = analysis_selection.unbind();
    let project: Bound<'py, PyAny> = compiled_project(py, request)?;
    if !on_progress.is_none() {
        let elapsed: f64 = monotonic(py)? - started;
        on_progress.call1((format!("Compiled project. ({elapsed:.2}s)"),))?;
    }
    project_graph(&project)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_compiled_project, module)?)?;
    module.add_function(wrap_pyfunction!(
        build_project_graph_with_analysis_selection,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(build_project_graph, module)?)
}
