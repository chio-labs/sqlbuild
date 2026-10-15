//! The compile-and-plan pipeline of execution commands: compile, rules gate, then planning.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PySet, PySetMethods};
use pyo3::{IntoPyObject, PyErr, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::phases::monotonic;
use crate::bindings::_helpers::compile_driver::pipeline_entries::{
    compile_analysis_selection, project_graph,
};
use crate::bindings::_helpers::compile_driver::plan_result::{
    PlanningInputs, connection_with_hooks, pipeline_result,
};
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, keywords,
};
use crate::bindings::_helpers::frontier::stage_capture::write_plan_capture;
use crate::bindings::_helpers::rules::results::{format_rules_result, rules_progress};
use crate::bindings::_helpers::rules::rules_config::load_rules_config;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const EFFECTIVE_CONFIG_MODULE: &str = "sqlbuild._native";
const COMPILE_EXCEPTIONS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const COMPILE_TYPES_MODULE: &str = "sqlbuild.compiler.compile.types";
const ANALYSIS_SELECTION_MODULE: &str = "sqlbuild._native";
const TIMING_TRACKER_MODULE: &str = "sqlbuild._native";
const RULE_EXCEPTIONS_MODULE: &str = "sqlbuild.rule_engine.exceptions";
const RULE_THREADS_MODULE: &str = "sqlbuild._native";
const RULE_MODELS_MODULE: &str = "sqlbuild.rule_engine.models";
const RUNTIME_MODELS_MODULE: &str = "sqlbuild.runtime.contracts.models";
const GENERIC_DIALECT: &str = "generic";

/// The current build's phase timing tracker, when one is recording.
fn timing_tracker(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    imported(py, TIMING_TRACKER_MODULE, "BuildPhaseTimingTracker")?.call_method0("current")
}

/// Report `message` through `on_progress` when a callback is set.
fn progress(on_progress: &Bound<'_, PyAny>, message: &str) -> PyResult<()> {
    if !on_progress.is_none() {
        on_progress.call1((message,))?;
    }
    Ok(())
}

/// Compile a project without opening a warehouse planning connection.
#[pyfunction]
#[pyo3(signature = (**options))]
fn compile_project_phase<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "compile_project_phase",
        options,
        (
            &["discovered_inputs", "adapter"],
            &["options", "on_progress"],
        ),
    )?;
    compiled_phase(
        (
            &arguments.value("discovered_inputs")?,
            &arguments.value("adapter")?,
        ),
        &arguments.value("options")?,
        &arguments.value("on_progress")?,
    )
}

/// `compile_project_phase` with resolved arguments.
fn compiled_phase<'py>(
    (discovered, adapter): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    options: &Bound<'py, PyAny>,
    on_progress: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let options: Bound<'py, PyAny> = if options.is_truthy()? {
        options.clone()
    } else {
        imported(py, NATIVE_RECORDS_MODULE, "CompilePipelineOptions")?.call0()?
    };
    let configured: Bound<'py, PyAny> = options.getattr("connection_config")?;
    let connection_config: Bound<'py, PyAny> = if configured.is_none() {
        call_with(
            &imported(
                py,
                EFFECTIVE_CONFIG_MODULE,
                "build_effective_connection_config",
            )?,
            &[
                ("discovered_inputs", discovered.clone()),
                ("selected_target", options.getattr("selected_target")?),
                ("cli_vars", options.getattr("cli_vars")?),
            ],
        )?
    } else {
        configured
    };
    progress(on_progress, "Compiling project...")?;
    let started: f64 = monotonic(py)?;
    let compiled: PyResult<Bound<'py, PyAny>> = (|| {
        let selection: Bound<'py, PyAny> = compile_analysis_selection(&options, discovered)?;
        call_with(
            &imported(py, NATIVE_MODULE, "build_compiled_project")?,
            &[
                ("discovered_inputs", discovered.clone()),
                ("adapter", adapter.clone()),
                ("selected_target", options.getattr("selected_target")?),
                ("no_sql_validation", options.getattr("no_sql_validation")?),
                ("cli_vars", options.getattr("cli_vars")?),
                (
                    "external_sql_reference_resolver",
                    options.getattr("external_sql_reference_resolver")?,
                ),
                ("resolved_connection", connection_config.clone()),
                ("analysis_selection", selection),
            ],
        )
    })();
    let compile_seconds: f64 = monotonic(py)? - started;
    let tracker: Bound<'py, PyAny> = timing_tracker(py)?;
    if !tracker.is_none() {
        tracker.setattr("compile_seconds", compile_seconds)?;
    }
    let project: Bound<'py, PyAny> = compiled?;
    reject_compile_errors(&project, &options, on_progress)?;
    progress(
        on_progress,
        &format!("Compiled project. ({compile_seconds:.2}s)"),
    )?;
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "CompiledProjectPhaseResult")?,
        &[
            ("project", project),
            ("connection_config", connection_config),
            (
                "compile_seconds",
                compile_seconds.into_pyobject(py)?.into_any(),
            ),
        ],
    )
}

/// Raise one `CompileInputError` listing every compile error the command must stop on.
fn reject_compile_errors(
    project: &Bound<'_, PyAny>,
    options: &Bound<'_, PyAny>,
    on_progress: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let py: Python<'_> = project.py();
    let plan_sql_tests: bool = options.getattr("plan_sql_tests")?.is_truthy()?;
    let sql_test: Bound<'_, PyAny> =
        imported(py, COMPILE_TYPES_MODULE, "CompiledResourceType")?.getattr("SQL_TEST")?;
    let mut errors: Vec<Bound<'_, PyAny>> = Vec::new();
    for diagnostic in project.getattr("diagnostics")?.try_iter()? {
        let diagnostic: Bound<'_, PyAny> = diagnostic?;
        if diagnostic.getattr("is_error")?.is_truthy()?
            && (plan_sql_tests || diagnostic.getattr("resource_type")?.ne(&sql_test)?)
        {
            errors.push(diagnostic);
        }
    }
    let Some(first) = errors.first() else {
        return Ok(());
    };
    progress(on_progress, "Project compilation failed.")?;
    let mut lines: Vec<String> = Vec::with_capacity(errors.len());
    let helps: Bound<'_, PySet> = PySet::empty(py)?;
    for diagnostic in &errors {
        let or_one = |name: &str| -> PyResult<String> {
            let value: Bound<'_, PyAny> = diagnostic.getattr(name)?;
            Ok(if value.is_truthy()? {
                value.str()?.to_string()
            } else {
                "1".to_owned()
            })
        };
        lines.push(format!(
            "[{}] {}:{}:{}: {}",
            diagnostic.getattr("code")?.str()?,
            diagnostic.getattr("path")?.str()?,
            or_one("line")?,
            or_one("column")?,
            diagnostic.getattr("message")?.str()?,
        ));
        helps.add(diagnostic.getattr("help")?)?;
    }
    let help: Bound<'_, PyAny> = if helps.len() == 1 {
        helps.pop().unwrap_or_else(|| py.None().into_bound(py))
    } else {
        py.None().into_bound(py)
    };
    let error: Bound<'_, PyAny> = imported(py, COMPILE_EXCEPTIONS_MODULE, "CompileInputError")?
        .call(
            (lines.join("\n"),),
            Some(&keywords(
                py,
                &[("code", first.getattr("code")?), ("help", help)],
            )?),
        )?;
    Err(PyErr::from_value(error))
}

/// Run compile inputs, assembly, planning, and manifest generation.
#[pyfunction]
#[pyo3(signature = (**options))]
fn run_compile_pipeline<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "run_compile_pipeline",
        options,
        (&["discovered_inputs", "adapter"], &["options", "hooks"]),
    )?;
    let discovered: Bound<'py, PyAny> = arguments.value("discovered_inputs")?;
    let adapter: Bound<'py, PyAny> = arguments.value("adapter")?;
    let options: Bound<'py, PyAny> = call_with(
        &imported(py, ANALYSIS_SELECTION_MODULE, "apply_unit_test_selectors")?,
        &[
            ("options", arguments.value("options")?),
            ("discovered_inputs", discovered.clone()),
        ],
    )?;
    let hooks: Bound<'py, PyAny> = arguments.value("hooks")?;
    let hooks: Bound<'py, PyAny> = if hooks.is_none() {
        imported(py, RUNTIME_MODELS_MODULE, "ConnectionHooks")?.call0()?
    } else {
        hooks
    };
    let on_progress: Bound<'py, PyAny> = hooks.getattr("on_progress")?;
    let compiled: Bound<'py, PyAny> =
        compiled_phase((&discovered, &adapter), &options, &on_progress)?;
    let project: Bound<'py, PyAny> = compiled.getattr("project")?;
    let graph: Bound<'py, PyAny> = project_graph(&project)?;
    run_rules_gate(
        (&discovered, &adapter),
        (&options, &on_progress),
        (&project, &graph),
    )?;
    planned((&discovered, &adapter), (&options, &hooks), &compiled)
}

/// Run the configured rules and stop the command when any of them finds a fault.
fn run_rules_gate<'py>(
    (discovered, adapter): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (options, on_progress): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (project, graph): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<()> {
    let py: Python<'py> = discovered.py();
    let rules_error: Bound<'py, PyAny> = imported(py, RULE_EXCEPTIONS_MODULE, "RulesError")?;
    let project_dir: Bound<'py, PyAny> = discovered.getattr("project_dir")?;
    if project_dir.is_none() {
        return Err(PyErr::from_value(
            rules_error.call1(("compiler rules require a resolved project directory",))?,
        ));
    }
    let mut config: Bound<'py, PyAny> =
        load_rules_config(py, project_dir.extract()?)?.into_bound(py);
    if options.getattr("no_cache")?.is_truthy()? {
        let cache: Bound<'py, PyAny> = call_with(
            &imported(py, NATIVE_RECORDS_MODULE, "RulesCacheConfig")?,
            &[("enabled", false.into_pyobject(py)?.to_owned().into_any())],
        )?;
        config = imported(py, "dataclasses", "replace")?
            .call((config,), Some(&keywords(py, &[("cache", cache)])?))?;
    }
    progress(on_progress, "Evaluating configured rules...")?;
    let started: f64 = monotonic(py)?;
    let dialect: Bound<'py, PyAny> = adapter.call_method0("sql_analysis_dialect")?;
    let dialect: Bound<'py, PyAny> = if dialect.is_truthy()? {
        dialect
    } else {
        GENERIC_DIALECT.into_pyobject(py)?.into_any()
    };
    let selected_keys: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            ANALYSIS_SELECTION_MODULE,
            "resolve_configured_rule_selection",
        )?,
        &[
            ("options", options.clone()),
            ("discovered_inputs", discovered.clone()),
            ("project", project.clone()),
        ],
    )?;
    let result: Bound<'py, PyAny> = call_with(
        &imported(py, RULE_THREADS_MODULE, "evaluate_rules")?,
        &[
            ("graph", graph.clone()),
            ("discovered_inputs", discovered.clone()),
            ("config", config),
            ("project_dir", project_dir),
            ("dialect", dialect),
            ("selected_keys", selected_keys),
            ("no_sql_analysis", options.getattr("no_sql_validation")?),
        ],
    )?;
    if !on_progress.is_none() {
        let elapsed: f64 = monotonic(py)? - started;
        let message: String = rules_progress(elapsed, &result, true)?;
        on_progress.call1((message,))?;
    }
    let findings: Bound<'py, PyAny> = result.getattr("findings")?;
    if !findings.is_truthy()? {
        return Ok(());
    }
    let summary: Bound<'py, PyAny> = call_with(
        &imported(py, RULE_MODELS_MODULE, "RulesResult")?,
        &[
            ("findings", findings),
            ("evaluated_models", result.getattr("evaluated_models")?),
            (
                "unevaluated_resources",
                result.getattr("unevaluated_resources")?,
            ),
            ("cache_hits", result.getattr("cache_hits")?),
            ("cache_misses", result.getattr("cache_misses")?),
        ],
    )?;
    let rendered: String = format_rules_result(&summary, false)?;
    Err(PyErr::from_value(rules_error.call1((format!(
        "configured compiler rules failed:\n{rendered}"
    ),))?))
}

/// Open the planning connection, plan, and record the compile and planning times.
fn planned<'py>(
    (discovered, adapter): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (options, hooks): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    compiled: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let tracker: Bound<'py, PyAny> = timing_tracker(py)?;
    let started: f64 = monotonic(py)?;
    let mut connection: Option<Bound<'py, PyAny>> = None;
    let result: PyResult<Bound<'py, PyAny>> = (|| {
        let opened: Bound<'py, PyAny> =
            connection_with_hooks(adapter, &compiled.getattr("connection_config")?, hooks)?;
        connection = Some(opened.clone());
        pipeline_result(
            &PlanningInputs {
                discovered_inputs: discovered,
                adapter,
                connection: &opened,
            },
            &compiled.getattr("project")?,
            options,
            &hooks.getattr("on_progress")?,
        )
    })();
    if let Some(connection) = connection.filter(|connection| !connection.is_none()) {
        adapter.call_method1("close", (connection,))?;
    }
    let planning_seconds: f64 = monotonic(py)? - started;
    if !tracker.is_none() {
        tracker.setattr("planning_seconds", planning_seconds)?;
    }
    let result: Bound<'py, PyAny> = result?;
    write_plan_capture(&result.getattr("plan_output")?)?;
    imported(py, "dataclasses", "replace")?.call(
        (result,),
        Some(&keywords(
            py,
            &[
                ("compile_seconds", compiled.getattr("compile_seconds")?),
                (
                    "planning_seconds",
                    planning_seconds.into_pyobject(py)?.into_any(),
                ),
            ],
        )?),
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(compile_project_phase, module)?)?;
    module.add_function(wrap_pyfunction!(run_compile_pipeline, module)?)
}
