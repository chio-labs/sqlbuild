//! The compile-and-plan pipeline of execution commands: compile, rules gate, then planning.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PySet, PySetMethods};
use pyo3::{IntoPyObject, PyErr, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_attachment::effective_config::build_effective_connection_config;
use crate::bindings::_helpers::compile_driver::phases::monotonic;
use crate::bindings::_helpers::compile_driver::pipeline_entries::{
    compile_analysis_selection, project_graph,
};
use crate::bindings::_helpers::compile_driver::plan_result::{
    PlanningInputs, connection_with_hooks, pipeline_result,
};
use crate::bindings::_helpers::compile_driver::project::build_compiled_project;
use crate::bindings::_helpers::compile_driver::python_calls::{KeywordArguments, keywords};
use crate::bindings::_helpers::compile_driver::selection_phases::{
    apply_unit_test_selectors, resolve_configured_rule_selection,
};
use crate::bindings::_helpers::diagnostics::trackers::current_tracker;
use crate::bindings::_helpers::frontier::stage_capture::write_plan_capture;
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::construct::{enum_member, new_record, new_record_with};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::replaced;
use crate::bindings::_helpers::records::ids::{ErrorId, RecordId};
use crate::bindings::_helpers::rules::results::{format_rules_result, rules_progress};
use crate::bindings::_helpers::rules::rule_dispatch::evaluate_rules;
use crate::bindings::_helpers::rules::rules_config::load_rules_config;

const GENERIC_DIALECT: &str = "generic";

/// The current build's phase timing tracker, when one is recording.
fn timing_tracker(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    current_tracker(py)
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
pub(crate) fn compile_project_phase<'py>(
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
        new_record(py, RecordId::CompilePipelineOptions, (), None)?
    };
    let configured: Bound<'py, PyAny> = native_field(&options, "connection_config")?;
    let connection_config: Bound<'py, PyAny> = if configured.is_none() {
        build_effective_connection_config(
            discovered,
            Some(native_field(&options, "selected_target")?),
            Some(native_field(&options, "cli_vars")?),
        )?
    } else {
        configured
    };
    progress(on_progress, "Compiling project...")?;
    let started: f64 = monotonic(py)?;
    let compiled: PyResult<Bound<'py, PyAny>> = (|| {
        let selection: Bound<'py, PyAny> = compile_analysis_selection(&options, discovered)?;
        build_compiled_project(
            py,
            Some(keywords(
                py,
                &[
                    ("discovered_inputs", discovered.clone()),
                    ("adapter", adapter.clone()),
                    (
                        "selected_target",
                        native_field(&options, "selected_target")?,
                    ),
                    (
                        "no_sql_validation",
                        native_field(&options, "no_sql_validation")?,
                    ),
                    ("cli_vars", native_field(&options, "cli_vars")?),
                    (
                        "external_sql_reference_resolver",
                        native_field(&options, "external_sql_reference_resolver")?,
                    ),
                    ("resolved_connection", connection_config.clone()),
                    ("analysis_selection", selection),
                ],
            )?),
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
    new_record_with(
        py,
        RecordId::CompiledProjectPhaseResult,
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
    let plan_sql_tests: bool = native_field(options, "plan_sql_tests")?.is_truthy()?;
    let sql_test: Bound<'_, PyAny> = enum_member(py, RecordId::CompiledResourceType, "SQL_TEST")?;
    let mut errors: Vec<Bound<'_, PyAny>> = Vec::new();
    for diagnostic in native_field(project, "diagnostics")?.try_iter()? {
        let diagnostic: Bound<'_, PyAny> = diagnostic?;
        if native_field(&diagnostic, "is_error")?.is_truthy()?
            && (plan_sql_tests || native_field(&diagnostic, "resource_type")?.ne(&sql_test)?)
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
            let value: Bound<'_, PyAny> = native_field(diagnostic, name)?;
            Ok(if value.is_truthy()? {
                value.str()?.to_string()
            } else {
                "1".to_owned()
            })
        };
        lines.push(format!(
            "[{}] {}:{}:{}: {}",
            native_field(diagnostic, "code")?.str()?,
            native_field(diagnostic, "path")?.str()?,
            or_one("line")?,
            or_one("column")?,
            native_field(diagnostic, "message")?.str()?,
        ));
        helps.add(native_field(diagnostic, "help")?)?;
    }
    let help: Bound<'_, PyAny> = if helps.len() == 1 {
        helps.pop().unwrap_or_else(|| py.None().into_bound(py))
    } else {
        py.None().into_bound(py)
    };
    let error: Bound<'_, PyAny> = error_class(py, ErrorId::CompileInput)?.call(
        (lines.join("\n"),),
        Some(&keywords(
            py,
            &[("code", native_field(first, "code")?), ("help", help)],
        )?),
    )?;
    Err(PyErr::from_value(error))
}

/// Run compile inputs, assembly, planning, and manifest generation.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn run_compile_pipeline<'py>(
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
    let options: Bound<'py, PyAny> =
        apply_unit_test_selectors(&arguments.value("options")?, &discovered)?;
    let hooks: Bound<'py, PyAny> = arguments.value("hooks")?;
    let hooks: Bound<'py, PyAny> = if hooks.is_none() {
        host::entry(py, ExecutorHost::ConnectionHooks)?.call0()?
    } else {
        hooks
    };
    let on_progress: Bound<'py, PyAny> = native_field(&hooks, "on_progress")?;
    let compiled: Bound<'py, PyAny> =
        compiled_phase((&discovered, &adapter), &options, &on_progress)?;
    let project: Bound<'py, PyAny> = native_field(&compiled, "project")?;
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
    let rules_error: Bound<'py, PyAny> = error_class(py, ErrorId::Rules)?;
    let project_dir: Bound<'py, PyAny> = native_field(discovered, "project_dir")?;
    if project_dir.is_none() {
        return Err(PyErr::from_value(
            rules_error.call1(("compiler rules require a resolved project directory",))?,
        ));
    }
    let mut config: Bound<'py, PyAny> =
        load_rules_config(py, project_dir.extract()?)?.into_bound(py);
    if native_field(options, "no_cache")?.is_truthy()? {
        let cache: Bound<'py, PyAny> = new_record_with(
            py,
            RecordId::RulesCacheConfig,
            &[("enabled", false.into_pyobject(py)?.to_owned().into_any())],
        )?;
        config = replaced(&config, &[("cache", cache)])?;
    }
    progress(on_progress, "Evaluating configured rules...")?;
    let started: f64 = monotonic(py)?;
    let dialect: Bound<'py, PyAny> = adapter.call_method0("sql_analysis_dialect")?;
    let dialect: Bound<'py, PyAny> = if dialect.is_truthy()? {
        dialect
    } else {
        GENERIC_DIALECT.into_pyobject(py)?.into_any()
    };
    let selected_keys: Bound<'py, PyAny> =
        resolve_configured_rule_selection(options, discovered, project)?;
    let result: Bound<'py, PyAny> = evaluate_rules(
        py,
        Some(keywords(
            py,
            &[
                ("graph", graph.clone()),
                ("discovered_inputs", discovered.clone()),
                ("config", config),
                ("project_dir", project_dir),
                ("dialect", dialect),
                ("selected_keys", selected_keys),
                (
                    "no_sql_analysis",
                    native_field(options, "no_sql_validation")?,
                ),
            ],
        )?),
    )?;
    if !on_progress.is_none() {
        let elapsed: f64 = monotonic(py)? - started;
        let message: String = rules_progress(elapsed, &result, true)?;
        on_progress.call1((message,))?;
    }
    let findings: Bound<'py, PyAny> = native_field(&result, "findings")?;
    if !findings.is_truthy()? {
        return Ok(());
    }
    let summary: Bound<'py, PyAny> = new_record_with(
        py,
        RecordId::RulesResult,
        &[
            ("findings", findings),
            (
                "evaluated_models",
                native_field(&result, "evaluated_models")?,
            ),
            (
                "unevaluated_resources",
                native_field(&result, "unevaluated_resources")?,
            ),
            ("cache_hits", native_field(&result, "cache_hits")?),
            ("cache_misses", native_field(&result, "cache_misses")?),
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
        let opened: Bound<'py, PyAny> = connection_with_hooks(
            adapter,
            &native_field(compiled, "connection_config")?,
            hooks,
        )?;
        connection = Some(opened.clone());
        pipeline_result(
            &PlanningInputs {
                discovered_inputs: discovered,
                adapter,
                connection: &opened,
            },
            &native_field(compiled, "project")?,
            options,
            &native_field(hooks, "on_progress")?,
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
    write_plan_capture(&native_field(&result, "plan_output")?)?;
    replaced(
        &result,
        &[
            (
                "compile_seconds",
                native_field(compiled, "compile_seconds")?,
            ),
            (
                "planning_seconds",
                planning_seconds.into_pyobject(py)?.into_any(),
            ),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(compile_project_phase, module)?)?;
    module.add_function(wrap_pyfunction!(run_compile_pipeline, module)?)
}
