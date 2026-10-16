//! Run built-in, SQL and custom rule phases on their threads and combine their findings.

use std::collections::HashMap;
use std::sync::Mutex;
use std::sync::atomic::Ordering;
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender, channel};
use std::thread::JoinHandle;
use std::time::Duration;

use pyo3::exceptions::{PyKeyboardInterrupt, PyRuntimeError};
use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyTuple};
use pyo3::{IntoPyObjectExt, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::cache::native_store::current_code_identity;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, within,
};
use crate::bindings::_helpers::rules::constants::TYPE_PROOF_RULE_CODES;
use crate::bindings::_helpers::rules::custom_evaluation::{
    CustomRun, evaluate_custom_rules_cached, outcome,
};
use crate::bindings::_helpers::rules::custom_hosts::HostCancel;
use crate::bindings::_helpers::rules::custom_rule_evidence::verify_custom_rules;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const RULES_MODELS_MODULE: &str = "sqlbuild._native";
const CUSTOM_PAYLOADS_MODULE: &str = "sqlbuild.rule_engine._helpers.engine.custom_payloads";
const CUSTOM_THREAD: &str = "sqlbuild-custom-rules";
const GENERIC_DIALECT: &str = "generic";
const PROJECT_RULES_OPTIONS: (&[&str], &[&str]) = (
    &["project", "config", "project_dir"],
    &["dialect", "verify_determinism"],
);
const NATIVE_RULES_OPTIONS: (&[&str], &[&str]) = (
    &["project", "config", "project_dir", "catalogue"],
    &[
        "dialect",
        "initial_findings",
        "defer_suppressions",
        "verify_determinism",
    ],
);
const CUSTOM_RULES_OPTIONS: (&[&str], &[&str]) = (
    &["project", "config", "project_dir", "rules", "dialect"],
    &["verify_determinism", "implementation_fingerprints"],
);
const RULES_THREAD: &str = "sqlbuild-rules";
/// How often a thread waiting for a rule phase checks for interrupts.
const JOIN_POLL: Duration = Duration::from_millis(100);
const EVALUATE_RULES_OPTIONS: (&[&str], &[&str]) = (
    &[
        "graph",
        "discovered_inputs",
        "config",
        "project_dir",
        "dialect",
    ],
    &[
        "selected_keys",
        "prepared_sql",
        "expansion_reuse",
        "no_sql_analysis",
    ],
);
const PREPARE_OPTIONS: (&[&str], &[&str]) = (
    &[
        "project_dir",
        "config",
        "discovered_inputs",
        "static_declaration_scope",
        "compiled_expansions",
        "stop",
    ],
    &[],
);

/// A running custom-rule evaluation, whose result is a `CustomRulesOutcome`.
type CustomHandle = PhaseThread;

/// A rule phase thread and the channel that disconnects when it finishes.
struct PhaseThread {
    handle: JoinHandle<PyResult<Py<PyAny>>>,
    finished: Receiver<()>,
}

impl PhaseThread {
    fn spawn(
        name: &str,
        phase: impl FnOnce() -> PyResult<Py<PyAny>> + Send + 'static,
    ) -> PyResult<Self> {
        let (sender, finished): (Sender<()>, Receiver<()>) = channel();
        let handle: JoinHandle<PyResult<Py<PyAny>>> = std::thread::Builder::new()
            .name(name.to_owned())
            .spawn(move || {
                let result: PyResult<Py<PyAny>> = phase();
                drop(sender);
                result
            })
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
        Ok(Self { handle, finished })
    }
}

/// The rule run one native evaluation describes; every field stays bound to its Python value.
struct NativeRun<'py> {
    project: Bound<'py, PyAny>,
    config: Bound<'py, PyAny>,
    project_dir: Bound<'py, PyAny>,
    catalogue: Bound<'py, PyAny>,
    dialect: String,
    verify_determinism: bool,
    initial_findings: Option<Bound<'py, PyAny>>,
    cancel: HostCancel,
}

/// How a native evaluation obtains its custom-rule outcome.
enum CustomSource {
    /// Already started (or nothing to start) by the caller.
    Started(Option<CustomHandle>),
    /// Start once the native request is built, beside the native evaluation.
    Deferred,
}

/// Evaluate the selected compiler rules over compiled models.
#[pyfunction]
#[pyo3(signature = (**options))]
fn evaluate_project_rules<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> =
        KeywordArguments::read(py, "evaluate_project_rules", options, PROJECT_RULES_OPTIONS)?;
    let project: Bound<'py, PyAny> = arguments.value("project")?;
    let config: Bound<'py, PyAny> = arguments.value("config")?;
    let project_dir: Bound<'py, PyAny> = arguments.value("project_dir")?;
    let dialect: String = dialect_argument(&arguments)?;
    let verify_determinism: bool = arguments.flag("verify_determinism")?;
    let effective: Bound<'py, PyAny> = call_with(
        &native(py, "resolve_rule_ignore_selectors")?,
        &[("config", config), ("project", project.clone())],
    )?;
    let catalogue: Bound<'py, PyAny> = call_with(
        &native(py, "build_rule_catalogue")?,
        &[
            ("config", effective.clone()),
            ("project_dir", project_dir.clone()),
        ],
    )?;
    let mut custom: bool = false;
    for rule in catalogue.try_iter()? {
        custom = custom || rule?.getattr("custom")?.is_truthy()?;
    }
    if custom {
        let rules: Bound<'py, PyAny> = call_with(
            &native(py, "select_catalogue_rules")?,
            &[
                ("catalogue", catalogue.clone()),
                ("config", effective.clone()),
                ("project_dir", project_dir.clone()),
            ],
        )?;
        verify_custom_rules(&rules, &project_dir)?;
    }
    let run: NativeRun<'py> = NativeRun {
        project,
        config: effective,
        project_dir,
        catalogue,
        dialect,
        verify_determinism,
        initial_findings: None,
        cancel: HostCancel::default(),
    };
    evaluate_native(&run, (false, None), CustomSource::Deferred)
}

/// Evaluate built-in rules natively with the catalogue's selected custom rules beside them.
#[pyfunction]
#[pyo3(signature = (**options))]
fn evaluate_native_rules<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> =
        KeywordArguments::read(py, "evaluate_native_rules", options, NATIVE_RULES_OPTIONS)?;
    let initial_findings: Bound<'py, PyAny> = arguments.value("initial_findings")?;
    let defer_suppressions: bool = arguments.flag("defer_suppressions")?;
    let run: NativeRun<'py> = NativeRun {
        project: arguments.value("project")?,
        config: arguments.value("config")?,
        project_dir: arguments.value("project_dir")?,
        catalogue: arguments.value("catalogue")?,
        dialect: dialect_argument(&arguments)?,
        verify_determinism: arguments.flag("verify_determinism")?,
        initial_findings: (!initial_findings.is_none()).then_some(initial_findings),
        cancel: HostCancel::default(),
    };
    evaluate_native(&run, (defer_suppressions, None), CustomSource::Deferred)
}

/// Evaluate custom rules through their incremental cache.
#[pyfunction]
#[pyo3(signature = (**options))]
fn evaluate_custom_rules<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> =
        KeywordArguments::read(py, "evaluate_custom_rules", options, CUSTOM_RULES_OPTIONS)?;
    let fingerprints: Bound<'py, PyAny> = arguments.value("implementation_fingerprints")?;
    evaluate_custom_rules_cached(CustomRun {
        project: &arguments.value("project")?,
        config: &arguments.value("config")?,
        project_dir: &arguments.value("project_dir")?,
        rules: arguments
            .value("rules")?
            .try_iter()?
            .collect::<PyResult<_>>()?,
        dialect: &arguments.value("dialect")?.extract::<String>()?,
        verify_determinism: arguments.flag("verify_determinism")?,
        implementation_fingerprints: if fingerprints.is_none() {
            HashMap::new()
        } else {
            fingerprints.extract()?
        },
        cancel: HostCancel::default(),
    })
}

/// The `dialect` argument, `"generic"` when it was not passed.
fn dialect_argument(arguments: &KeywordArguments<'_>) -> PyResult<String> {
    if arguments.passed("dialect")? {
        return arguments.value("dialect")?.extract();
    }
    Ok(GENERIC_DIALECT.to_owned())
}

/// Evaluate independent rule phases concurrently, then finalize their combined findings.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn evaluate_rules<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> =
        KeywordArguments::read(py, "evaluate_rules", options, EVALUATE_RULES_OPTIONS)?;
    let graph: Bound<'py, PyAny> = arguments.value("graph")?;
    let dialect: Bound<'py, PyAny> = arguments.value("dialect")?;
    let plan: Bound<'py, PyAny> = call_with(
        &native(py, "plan_rule_run")?,
        &[
            ("graph", graph.clone()),
            ("config", arguments.value("config")?),
            ("project_dir", arguments.value("project_dir")?),
            ("selected_keys", arguments.value("selected_keys")?),
            (
                "no_sql_analysis",
                arguments.value_or_false("no_sql_analysis")?,
            ),
        ],
    )?;
    let run: NativeRun<'py> = NativeRun {
        project: plan.getattr("project")?,
        config: plan.getattr("config")?,
        project_dir: plan.getattr("project_dir")?,
        catalogue: plan.getattr("catalogue")?,
        dialect: dialect.extract()?,
        verify_determinism: false,
        initial_findings: None,
        cancel: HostCancel::default(),
    };
    let payloads: Bound<'py, PyAny> = plan.getattr("custom_payloads")?;
    let custom: Option<CustomHandle> = start_custom_rules(&run, &payloads)?;
    let native_run: [Py<PyAny>; 5] = [
        run.project.clone().unbind(),
        run.config.clone().unbind(),
        run.project_dir.clone().unbind(),
        run.catalogue.clone().unbind(),
        payloads.clone().unbind(),
    ];
    let native_dialect: String = run.dialect.clone();
    let native_cancel: HostCancel = run.cancel.clone();
    let native_thread: PhaseThread = PhaseThread::spawn(RULES_THREAD, move || {
        Python::attach(|py| {
            let [project, config, project_dir, catalogue, payloads] = native_run;
            let run: NativeRun<'_> = NativeRun {
                project: project.into_bound(py),
                config: config.into_bound(py),
                project_dir: project_dir.into_bound(py),
                catalogue: catalogue.into_bound(py),
                dialect: native_dialect,
                verify_determinism: false,
                initial_findings: None,
                cancel: native_cancel,
            };
            evaluate_native(
                &run,
                (true, Some(payloads.into_bound(py))),
                CustomSource::Started(custom),
            )
            .map(Bound::unbind)
        })
    })?;
    let sql_result: PyResult<Bound<'py, PyAny>> = call_with(
        &native(py, "run_planned_sql_rules")?,
        &[
            ("plan", plan.clone()),
            ("graph", graph),
            ("discovered_inputs", arguments.value("discovered_inputs")?),
            ("dialect", dialect),
            ("prepared_sql", arguments.value("prepared_sql")?),
            ("expansion_reuse", arguments.value("expansion_reuse")?),
        ],
    );
    cancel_on_interrupt(py, &sql_result, &run.cancel);
    let result: PyResult<Bound<'py, PyAny>> = joined(py, native_thread, &run.cancel);
    let sql_result: Bound<'py, PyAny> = sql_result?;
    let result: Bound<'py, PyAny> = result?;
    call_with(
        &native(py, "finish_rule_run")?,
        &[
            ("plan", plan),
            ("sql_result", sql_result),
            ("result", result),
        ],
    )
}

/// Start early SQL lint on `executor` when the project selects SQL rules without a cache.
#[pyfunction]
#[pyo3(signature = (*, inputs, executor, dialect, stop))]
pub(crate) fn prepare_sql_rules<'py>(
    inputs: &Bound<'py, PyAny>,
    executor: &Bound<'py, PyAny>,
    dialect: &Bound<'py, PyAny>,
    stop: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = inputs.py();
    let preparation: Bound<'py, PyAny> = call_with(
        &native(py, "sql_lint_preparation")?,
        &[("inputs", inputs.clone()), ("dialect", dialect.clone())],
    )?;
    if preparation.is_none() {
        return Ok(preparation);
    }
    let (project_dir, codes, config): (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>) =
        preparation.extract()?;
    let expansions: Bound<'py, PyAny> =
        native(py, "early_lint_expansions")?.call1((inputs.getattr("model_inputs")?,))?;
    let work: Bound<'py, PyDict> = PyDict::new(py);
    work.set_item("project_dir", &project_dir)?;
    work.set_item("config", config)?;
    work.set_item("discovered_inputs", inputs.getattr("discovered_inputs")?)?;
    work.set_item(
        "static_declaration_scope",
        inputs.getattr("declaration_scope")?,
    )?;
    work.set_item("compiled_expansions", expansions)?;
    work.set_item("stop", stop)?;
    let future: Bound<'py, PyAny> = executor.call_method(
        "submit",
        (wrap_pyfunction!(prepare_early_sql_lint, py)?,),
        Some(&work),
    )?;
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "PreparedSqlLint")?,
        &[
            ("codes", codes),
            ("project_dir", project_dir),
            ("future", future),
        ],
    )
}

/// Expand and lint SQL early, stopping when `stop` is set; runs on the early-lint executor.
#[pyfunction]
#[pyo3(signature = (**options))]
fn prepare_early_sql_lint<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> =
        KeywordArguments::read(py, "prepare_early_sql_lint", options, PREPARE_OPTIONS)?;
    let project_dir: Bound<'py, PyAny> = arguments.value("project_dir")?;
    let discovered_inputs: Bound<'py, PyAny> = arguments.value("discovered_inputs")?;
    let scope: Bound<'py, PyAny> =
        native(py, "lint_stop_scope")?.call1((arguments.value("stop")?,))?;
    within(&scope, |_| {
        let context: Bound<'py, PyAny> = call_with(
            &native(py, "build_lint_expansion_context")?,
            &[
                ("project_dir", project_dir.clone()),
                ("discovered_inputs", discovered_inputs.clone()),
                (
                    "static_declaration_scope",
                    arguments.value("static_declaration_scope")?,
                ),
            ],
        )?;
        let result: Bound<'py, PyAny> = call_with(
            &native(py, "run_lint")?,
            &[
                ("project_dir", project_dir.clone()),
                ("config", arguments.value("config")?),
                ("discovered_inputs", discovered_inputs.clone()),
                (
                    "compiled_expansions",
                    arguments.value("compiled_expansions")?,
                ),
                ("expansion_context", context.clone()),
            ],
        )?;
        call_with(
            &imported(py, NATIVE_RECORDS_MODULE, "PreparedSqlLintResult")?,
            &[("result", result), ("context", context)],
        )
    })
}

/// Evaluate built-in rules natively while custom rules run beside them.
fn evaluate_native<'py>(
    run: &NativeRun<'py>,
    (defer_suppressions, custom_payloads): (bool, Option<Bound<'py, PyAny>>),
    custom: CustomSource,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = run.project.py();
    let prepared: PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> =
        native_request(run, custom_payloads);
    let custom: Option<CustomHandle> = match (custom, &prepared) {
        (CustomSource::Started(handle), Ok(_)) => handle,
        (CustomSource::Started(handle), Err(_)) => {
            if let Some(handle) = handle {
                let _abandoned: PyResult<Bound<'py, PyAny>> = joined(py, handle, &run.cancel);
            }
            None
        }
        (CustomSource::Deferred, Ok((payloads, _))) => start_custom_rules(run, payloads)?,
        (CustomSource::Deferred, Err(_)) => None,
    };
    let (_, request): (Bound<'py, PyAny>, Bound<'py, PyAny>) = prepared?;
    let evaluated: PyResult<Bound<'py, PyAny>> =
        native(py, "evaluate_rules_request").and_then(|evaluate| evaluate.call1((request,)));
    cancel_on_interrupt(py, &evaluated, &run.cancel);
    let custom: PyResult<Bound<'py, PyAny>> = match custom {
        Some(handle) => joined(py, handle, &run.cancel),
        None => outcome(py, (Vec::new(), 0, 0), (0, 0)),
    };
    let native_result: Bound<'py, PyAny> = evaluated?;
    let custom: Bound<'py, PyAny> = custom?;
    let mut findings: Bound<'py, PyAny> = PyTuple::new(
        py,
        native_result
            .getattr("findings")?
            .try_iter()?
            .chain(custom.getattr("findings")?.try_iter()?)
            .collect::<PyResult<Vec<_>>>()?,
    )?
    .into_any();
    if !defer_suppressions {
        findings = call_with(
            &native(py, "finalize_rule_findings_rows")?,
            &[
                ("config", run.config.clone()),
                ("project_dir", run.project_dir.clone()),
                ("evaluated_codes", native_result.getattr("selected_codes")?),
                ("findings", findings),
            ],
        )?;
    }
    let reused: bool = native_result.getattr("reused")?.is_truthy()?;
    let native_hits: i64 = native_result.getattr("cache_hits")?.extract()?;
    let native_misses: i64 = native_result.getattr("cache_misses")?.extract()?;
    let custom_hits: i64 = custom.getattr("cache_hits")?.extract()?;
    let custom_misses: i64 = custom.getattr("cache_misses")?.extract()?;
    call_with(
        &imported(py, RULES_MODELS_MODULE, "RulesResult")?,
        &[
            ("findings", findings),
            (
                "evaluated_models",
                native_result.getattr("evaluated_models")?,
            ),
            (
                "cache_hits",
                (if reused {
                    native_hits + native_misses
                } else {
                    native_hits
                } + custom_hits)
                    .into_bound_py_any(py)?,
            ),
            (
                "cache_misses",
                (if reused { 0 } else { native_misses } + custom_misses).into_bound_py_any(py)?,
            ),
            (
                "built_in_ms",
                if reused {
                    0.into_bound_py_any(py)?
                } else {
                    native_result.getattr("built_in_ms")?
                },
            ),
            ("custom_ms", custom.getattr("custom_ms")?),
            ("custom_cpu_ms", custom.getattr("custom_cpu_ms")?),
        ],
    )
}

/// The custom-rule payloads and the native rules request of one evaluation.
fn native_request<'py>(
    run: &NativeRun<'py>,
    custom_payloads: Option<Bound<'py, PyAny>>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py: Python<'py> = run.project.py();
    let payloads: Bound<'py, PyAny> = match custom_payloads {
        Some(payloads) => payloads,
        None => call_with(
            &imported(py, CUSTOM_PAYLOADS_MODULE, "custom_rule_payloads")?,
            &[
                ("catalogue", run.catalogue.clone()),
                ("project_dir", run.project_dir.clone()),
            ],
        )?,
    };
    let mut include_type_proof: bool = false;
    for code in TYPE_PROOF_RULE_CODES {
        include_type_proof = include_type_proof
            || call_with(
                &native(py, "rule_selected")?,
                &[
                    ("config", run.config.clone()),
                    ("code", pyo3::types::PyString::new(py, code).into_any()),
                ],
            )?
            .is_truthy()?;
    }
    let request: Bound<'py, PyAny> = call_with(
        &native(py, "build_rules_request")?,
        &[
            ("project", run.project.clone()),
            ("config", run.config.clone()),
            ("project_dir", run.project_dir.clone()),
            ("dialect", run.dialect.clone().into_bound_py_any(py)?),
            (
                "initial_findings",
                run.initial_findings
                    .clone()
                    .unwrap_or_else(|| PyTuple::empty(py).into_any()),
            ),
            ("custom_payloads", payloads.clone()),
            (
                "include_type_proof",
                include_type_proof.into_bound_py_any(py)?,
            ),
        ],
    )?;
    Ok((payloads, request))
}

/// Start the selected custom rules on their thread after digesting installed code here.
fn start_custom_rules(
    run: &NativeRun<'_>,
    payloads: &Bound<'_, PyAny>,
) -> PyResult<Option<CustomHandle>> {
    let py: Python<'_> = run.project.py();
    if !payloads.is_truthy()? {
        return Ok(None);
    }
    let selected: Bound<'_, PyFrozenSet> = PyFrozenSet::new(
        py,
        call_with(
            &native(py, "selected_rule_codes")?,
            &[
                ("config", run.config.clone()),
                ("custom_payloads", payloads.clone()),
            ],
        )?
        .try_iter()?
        .collect::<PyResult<Vec<_>>>()?,
    )?;
    let mut rules: Vec<Py<PyAny>> = Vec::new();
    for rule in run.catalogue.try_iter()? {
        let rule: Bound<'_, PyAny> = rule?;
        if rule.getattr("custom")?.is_truthy()? && selected.contains(rule.getattr("code")?)? {
            rules.push(rule.unbind());
        }
    }
    if rules.is_empty() {
        return Ok(None);
    }
    if run
        .config
        .getattr("cache")?
        .getattr("enabled")?
        .is_truthy()?
    {
        let _identity: String = current_code_identity(py)?;
    }
    let mut fingerprints: HashMap<String, String> = HashMap::new();
    for payload in payloads.try_iter()? {
        let payload: Bound<'_, PyAny> = payload?;
        fingerprints.insert(
            payload.get_item("code")?.str()?.extract()?,
            payload
                .get_item("implementation_fingerprint")?
                .str()?
                .extract()?,
        );
    }
    let inputs: [Py<PyAny>; 3] = [
        run.project.clone().unbind(),
        run.config.clone().unbind(),
        run.project_dir.call_method0("resolve")?.unbind(),
    ];
    let dialect: String = run.dialect.clone();
    let verify_determinism: bool = run.verify_determinism;
    let cancel: HostCancel = run.cancel.clone();
    PhaseThread::spawn(CUSTOM_THREAD, move || {
        Python::attach(|py| {
            let [project, config, project_dir] = inputs;
            evaluate_custom_rules_cached(CustomRun {
                project: project.bind(py),
                config: config.bind(py),
                project_dir: project_dir.bind(py),
                rules: rules.into_iter().map(|rule| rule.into_bound(py)).collect(),
                dialect: &dialect,
                verify_determinism,
                implementation_fingerprints: fingerprints,
                cancel,
            })
            .map(Bound::unbind)
        })
    })
    .map(Some)
}

/// Wait for a phase thread off the interpreter; an interrupt cancels the run's hosts first.
fn joined<'py>(
    py: Python<'py>,
    phase: PhaseThread,
    cancel: &HostCancel,
) -> PyResult<Bound<'py, PyAny>> {
    let finished: Mutex<Receiver<()>> = Mutex::new(phase.finished);
    let mut signal: Option<PyErr> = None;
    loop {
        let waited: Result<(), RecvTimeoutError> = py.detach(|| match finished.lock() {
            Ok(receiver) => receiver.recv_timeout(JOIN_POLL),
            Err(_) => Err(RecvTimeoutError::Disconnected),
        });
        match waited {
            Ok(()) | Err(RecvTimeoutError::Disconnected) => break,
            Err(RecvTimeoutError::Timeout) => {
                if signal.is_none()
                    && let Err(error) = py.check_signals()
                {
                    cancel.store(true, Ordering::Release);
                    signal = Some(error);
                }
            }
        }
    }
    let joined: PyResult<Py<PyAny>> = py
        .detach(|| phase.handle.join())
        .map_err(|_| PyRuntimeError::new_err("rules thread panicked"))?;
    if let Some(error) = signal {
        return Err(error);
    }
    joined.map(|value| value.into_bound(py))
}

/// Cancel the run's custom-rule hosts when `result` is an interrupt.
fn cancel_on_interrupt(py: Python<'_>, result: &PyResult<Bound<'_, PyAny>>, cancel: &HostCancel) {
    if let Err(error) = result
        && error.is_instance_of::<PyKeyboardInterrupt>(py)
    {
        cancel.store(true, Ordering::Release);
    }
}

fn native<'py>(py: Python<'py>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    imported(py, NATIVE_MODULE, name)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(evaluate_project_rules, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate_native_rules, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate_custom_rules, module)?)?;
    module.add_function(wrap_pyfunction!(evaluate_rules, module)?)?;
    module.add_function(wrap_pyfunction!(prepare_sql_rules, module)?)?;
    module.add_function(wrap_pyfunction!(prepare_early_sql_lint, module)?)
}
