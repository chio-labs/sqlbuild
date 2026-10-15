//! The compile analysis sequence: discovery, graph, lineage, contracts, selection and rules.

use std::time::Instant;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyString, PyTuple, PyTupleMethods};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::command_runtime::adapters::resolve_cli_adapter;
use crate::bindings::_helpers::compile_driver::python_calls::{
    Status, call_with, imported, keywords, within,
};
use crate::bindings::_helpers::rules::constants::RULE_FIX_AVAILABLE_NOTE;
use crate::bindings::_helpers::rules::early_sql_lint::EarlySqlLint;
use crate::bindings::_helpers::rules::results::rules_progress;
use crate::bindings::_helpers::rules::rules_config::load_rules_config;

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const DISCOVER_MODULE: &str = "sqlbuild._native";
const REJECT_SELECTORS_MODULE: &str = "sqlbuild._native";
const ADAPTER_NAME_MODULE: &str = "sqlbuild._native";
const LIFECYCLE_MODULE: &str = "sqlbuild.runtime.observability.classes.operation_lifecycle";
const SELECTED_GRAPH_MODULE: &str = "sqlbuild._native";
const RICH_LINEAGE: &str = "rich";
const FAST_LINEAGE: &str = "fast";
const RICH_COLUMN_LINEAGE: &str = "RICH";
const FAST_COLUMN_LINEAGE: &str = "FAST";

const CONTRACTS_MODULE: &str = "sqlbuild._native";
const CONTRACT_MODELS_MODULE: &str = "sqlbuild._native";
const SELECTION_MODULE: &str = "sqlbuild._native";
const RULE_THREADS_MODULE: &str = "sqlbuild._native";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const CLI_COMPILE_MODELS_MODULE: &str = "sqlbuild._native";
const GENERIC_DIALECT: &str = "generic";
const TARGET_DIRECTORY: &str = "target";

/// `ColumnLineageMode.<member>`.
fn column_lineage_mode<'py>(py: Python<'py>, member: &str) -> PyResult<Bound<'py, PyAny>> {
    imported(py, NATIVE_RECORDS_MODULE, "ColumnLineageMode")?.getattr(member)
}

/// Column lineage in the compile's mode; `none` skips the analyzer.
fn compile_lineage<'py>(
    graph: &Bound<'py, PyAny>,
    dialect: &Bound<'py, PyAny>,
    mode: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = graph.py();
    let member: &str = if mode.eq(RICH_LINEAGE)? {
        RICH_COLUMN_LINEAGE
    } else if mode.eq(FAST_LINEAGE)? {
        FAST_COLUMN_LINEAGE
    } else {
        return Ok(py.None().into_bound(py));
    };
    imported(py, "sqlbuild._native", "build_project_column_lineage")?.call1((
        graph.getattr("project")?,
        dialect,
        column_lineage_mode(py, member)?,
        py.None(),
    ))
}

/// Milliseconds since `start`, truncated as Python's `int((monotonic() - start) * 1000)`.
fn elapsed_ms(start: Instant) -> u64 {
    (start.elapsed().as_secs_f64() * 1000.0) as u64
}

/// The compile command's options, read by keyword as Python's signature named them.
struct AnalysisOptions<'py> {
    project_dir: Bound<'py, PyAny>,
    no_sql_validation: Bound<'py, PyAny>,
    selected_target: Bound<'py, PyAny>,
    lineage_mode: Bound<'py, PyAny>,
    cli_vars: Bound<'py, PyAny>,
    profile_flags: Bound<'py, PyAny>,
    analysis_selection: Bound<'py, PyAny>,
    status: Bound<'py, PyAny>,
    prepared_artifacts: Bound<'py, PyAny>,
}

impl<'py> AnalysisOptions<'py> {
    fn read(py: Python<'py>, options: &Bound<'py, PyDict>) -> PyResult<Self> {
        let required = |name: &str| -> PyResult<Bound<'py, PyAny>> {
            options.get_item(name)?.ok_or_else(|| {
                pyo3::exceptions::PyTypeError::new_err(format!(
                    "analyze_compile_project() missing 1 required keyword-only argument: '{name}'"
                ))
            })
        };
        Ok(Self {
            project_dir: required("project_dir")?,
            no_sql_validation: required("no_sql_validation")?,
            selected_target: required("selected_target")?,
            lineage_mode: required("lineage_mode")?,
            cli_vars: required("cli_vars")?,
            profile_flags: required("profile_flags")?,
            analysis_selection: required("analysis_selection")?,
            status: required("status")?,
            prepared_artifacts: options
                .get_item("prepared_artifacts")?
                .unwrap_or_else(|| py.None().into_bound(py)),
        })
    }
}

/// `{seconds:.2f}`, as Python formats elapsed milliseconds over a thousand.
fn seconds(milliseconds: u64) -> String {
    format!("{:.2}", milliseconds as f64 / 1000.0)
}

/// Whether any of `diagnostics` is an error.
fn any_error(diagnostics: &Bound<'_, PyAny>) -> PyResult<bool> {
    for diagnostic in diagnostics.try_iter()? {
        if diagnostic?.getattr("is_error")?.is_truthy()? {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Discover, compile and validate the project into one `CompileAnalysis`.
#[pyfunction]
#[pyo3(signature = (**options))]
fn analyze_compile_project<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    analyze(py, &options.unwrap_or_else(|| PyDict::new(py)))
}

/// `analyze_compile_project` with its keyword options.
pub(crate) fn analyze<'py>(
    py: Python<'py>,
    options: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    let options: AnalysisOptions<'py> = AnalysisOptions::read(py, options)?;
    let selection: &Bound<'py, PyAny> = &options.analysis_selection;
    let enabled: bool = !(selection.getattr("select")?.is_truthy()?
        || selection.getattr("exclude")?.is_truthy()?);
    let manager: Bound<'py, PyAny> = Bound::new(py, EarlySqlLint::new(py, enabled)?)?.into_any();
    within(&manager, |early_lint| analyzed(py, &options, early_lint))
}

/// The analysis phases sharing the command options, status line and early SQL lint.
struct Driver<'a, 'py> {
    py: Python<'py>,
    options: &'a AnalysisOptions<'py>,
    status: Status<'py>,
    early_lint: &'a Bound<'py, PyAny>,
    select: Bound<'py, PyAny>,
    exclude: Bound<'py, PyAny>,
}

/// Contract validation's result with its wall and thread CPU milliseconds.
struct ContractPhase<'py> {
    result: Bound<'py, PyAny>,
    wall_ms: u64,
    cpu_ms: i64,
}

/// `_analyze_compile_project`.
fn analyzed<'py>(
    py: Python<'py>,
    options: &AnalysisOptions<'py>,
    early_lint: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let driver: Driver<'_, 'py> = Driver {
        py,
        options,
        status: Status(options.status.clone()),
        early_lint,
        select: options.analysis_selection.getattr("select")?,
        exclude: options.analysis_selection.getattr("exclude")?,
    };
    let (discovered, discover_ms): (Bound<'py, PyAny>, u64) = driver.discover()?;
    let adapter: Bound<'py, PyAny> = driver.adapter(&discovered)?;
    let dialect: Bound<'py, PyAny> = adapter.call_method0("sql_analysis_dialect")?;
    let lint_dialect: Bound<'py, PyAny> = if dialect.is_truthy()? {
        dialect.clone()
    } else {
        PyString::new(py, GENERIC_DIALECT).into_any()
    };
    let (graph, graph_ms): (Bound<'py, PyAny>, u64) =
        driver.graph((&discovered, &adapter), &lint_dialect)?;
    let project: Bound<'py, PyAny> = graph.getattr("project")?;
    let graph_failed: bool = any_error(&project.getattr("diagnostics")?)?;
    let mut early_lint_wait_ms: Bound<'py, PyAny> = 0_i64.into_pyobject(py)?.into_any();
    if graph_failed {
        early_lint_wait_ms = early_lint.call_method0("stop")?;
    }
    let (lineage, lineage_ms): (Bound<'py, PyAny>, u64) = driver.lineage(&graph, &dialect)?;
    let contracts: ContractPhase<'py> = driver.contracts(&project, &dialect)?;
    let selected_keys: Bound<'py, PyAny> = call_with(
        &imported(py, SELECTION_MODULE, "select_project_graph")?,
        &[
            ("graph", graph.clone()),
            ("select", driver.select.clone()),
            ("exclude", driver.exclude.clone()),
        ],
    )?;
    let core_diagnostics: Bound<'py, PyTuple> = PyTuple::new(
        py,
        project
            .getattr("diagnostics")?
            .try_iter()?
            .chain(contracts.result.getattr("diagnostics")?.try_iter()?)
            .collect::<PyResult<Vec<_>>>()?,
    )?;
    let rules_result: Bound<'py, PyAny> = if graph_failed {
        empty_rules_result(py)?
    } else {
        let result: Bound<'py, PyAny> = driver.rules(
            (&graph, &discovered, &adapter),
            (&core_diagnostics, &selected_keys),
            &lint_dialect,
        )?;
        early_lint_wait_ms = early_lint.call_method0("stop")?;
        result
    };
    let diagnostics: Bound<'py, PyTuple> =
        with_rule_diagnostics(py, &core_diagnostics, &rules_result)?;
    call_with(
        &imported(py, CLI_COMPILE_MODELS_MODULE, "CompileAnalysis")?,
        &[
            ("discovered_inputs", discovered),
            ("adapter", adapter),
            ("graph", graph),
            ("selected_keys", selected_keys),
            ("lineage", lineage),
            ("diagnostics", diagnostics.into_any()),
            ("discover_ms", discover_ms.into_pyobject(py)?.into_any()),
            ("graph_ms", graph_ms.into_pyobject(py)?.into_any()),
            ("lineage_ms", lineage_ms.into_pyobject(py)?.into_any()),
            (
                "contract_ms",
                contracts.wall_ms.into_pyobject(py)?.into_any(),
            ),
            (
                "contract_cpu_ms",
                contracts.cpu_ms.into_pyobject(py)?.into_any(),
            ),
            ("built_in_rules_ms", rules_result.getattr("built_in_ms")?),
            ("custom_rules_ms", rules_result.getattr("custom_ms")?),
            (
                "custom_rules_cpu_ms",
                rules_result.getattr("custom_cpu_ms")?,
            ),
            ("early_lint_wait_ms", early_lint_wait_ms),
            ("rule_cache_hits", rules_result.getattr("cache_hits")?),
            ("rule_cache_misses", rules_result.getattr("cache_misses")?),
            (
                "skipped_type_proof_rules",
                rules_result.getattr("skipped_type_proof_rules")?,
            ),
        ],
    )
}

/// `RulesRunResult` of a compile whose rules did not run.
fn empty_rules_result(py: Python<'_>) -> PyResult<Bound<'_, PyAny>> {
    let zero: Bound<'_, PyAny> = 0_i64.into_pyobject(py)?.into_any();
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "RulesRunResult")?,
        &[
            ("findings", PyTuple::empty(py).into_any()),
            ("evaluated_models", zero.clone()),
            ("built_in_ms", zero.clone()),
            ("custom_ms", zero),
        ],
    )
}

impl<'py> Driver<'_, 'py> {
    /// Discover the project inputs and reject unit-test selectors.
    fn discover(&self) -> PyResult<(Bound<'py, PyAny>, u64)> {
        let py: Python<'py> = self.py;
        let started: Instant = Instant::now();
        self.status.start("Discovering project...")?;
        let false_value: Bound<'py, PyAny> = PyBool::new(py, false).to_owned().into_any();
        let override_analysis: Bound<'py, PyAny> = if self
            .options
            .profile_flags
            .getattr("skip_discovery_sql_analysis")?
            .is_truthy()?
        {
            false_value.clone()
        } else {
            py.None().into_bound(py)
        };
        let discovered: Bound<'py, PyAny> = call_with(
            &imported(py, DISCOVER_MODULE, "discover_project_inputs")?,
            &[
                ("project_dir", self.options.project_dir.clone()),
                ("extract_output_column_locations", false_value),
                ("sql_analysis_enabled_override", override_analysis),
            ],
        )?;
        call_with(
            &imported(py, REJECT_SELECTORS_MODULE, "reject_unit_test_selectors")?,
            &[
                ("select", self.select.clone()),
                ("exclude", self.exclude.clone()),
                ("discovered_inputs", discovered.clone()),
            ],
        )?;
        let discover_ms: u64 = elapsed_ms(started);
        self.status
            .complete(&format!("Discovered project. ({}s)", seconds(discover_ms)))?;
        Ok((discovered, discover_ms))
    }

    /// The adapter the project and local configuration select.
    fn adapter(&self, discovered: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
        let adapter_name: Bound<'py, PyAny> = call_with(
            &imported(
                self.py,
                ADAPTER_NAME_MODULE,
                "resolve_effective_adapter_name",
            )?,
            &[
                ("project_config", discovered.getattr("project_config")?),
                ("local_config", discovered.getattr("local_config")?),
            ],
        )?;
        resolve_cli_adapter(&adapter_name, &self.options.project_dir)
    }

    /// Compile the project graph, starting the early SQL lint once inputs are ready.
    fn graph(
        &self,
        (discovered, adapter): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
        lint_dialect: &Bound<'py, PyAny>,
    ) -> PyResult<(Bound<'py, PyAny>, u64)> {
        let py: Python<'py> = self.py;
        let options: &AnalysisOptions<'py> = self.options;
        let started: Instant = Instant::now();
        self.status.start("Compiling project graph...")?;
        let lifecycle: Bound<'py, PyAny> = call_with(
            &imported(py, LIFECYCLE_MODULE, "OperationLifecycle")?,
            &[
                ("operation_kind", PyString::new(py, "project").into_any()),
                (
                    "operation_name",
                    PyString::new(py, "project_compile").into_any(),
                ),
            ],
        )?;
        let on_inputs_ready: Bound<'py, PyAny> = imported(py, "functools", "partial")?.call(
            (self.early_lint.getattr("start")?,),
            Some(&keywords(py, &[("dialect", lint_dialect.clone())])?),
        )?;
        let analysis_selection: Bound<'py, PyAny> = imported(py, "dataclasses", "replace")?.call(
            (options.analysis_selection.clone(),),
            Some(&keywords(py, &[("on_inputs_ready", on_inputs_ready)])?),
        )?;
        let lineage_mode: Bound<'py, PyAny> = column_lineage_mode(
            py,
            if options.lineage_mode.eq(RICH_LINEAGE)? {
                RICH_COLUMN_LINEAGE
            } else {
                FAST_COLUMN_LINEAGE
            },
        )?;
        let graph: Bound<'py, PyAny> = within(&lifecycle, |_| {
            call_with(
                &imported(
                    py,
                    SELECTED_GRAPH_MODULE,
                    "build_project_graph_with_analysis_selection",
                )?,
                &[
                    ("discovered_inputs", discovered.clone()),
                    ("adapter", adapter.clone()),
                    ("selected_target", options.selected_target.clone()),
                    ("no_sql_validation", options.no_sql_validation.clone()),
                    (
                        "skip_column_inference",
                        options.profile_flags.getattr("skip_column_inference")?,
                    ),
                    ("column_lineage_mode", lineage_mode),
                    ("cli_vars", options.cli_vars.clone()),
                    ("analysis_selection", analysis_selection),
                ],
            )
        })?;
        let graph_ms: u64 = elapsed_ms(started);
        self.status
            .complete(&format!("Compiled project graph. ({}s)", seconds(graph_ms)))?;
        Ok((graph, graph_ms))
    }

    /// Column lineage in the requested mode.
    fn lineage(
        &self,
        graph: &Bound<'py, PyAny>,
        dialect: &Bound<'py, PyAny>,
    ) -> PyResult<(Bound<'py, PyAny>, u64)> {
        let started: Instant = Instant::now();
        self.status.start("Analyzing column lineage...")?;
        let lineage: Bound<'py, PyAny> =
            compile_lineage(graph, dialect, &self.options.lineage_mode)?;
        let lineage_ms: u64 = elapsed_ms(started);
        self.status.complete(&format!(
            "Analyzed column lineage. ({}s)",
            seconds(lineage_ms)
        ))?;
        Ok((lineage, lineage_ms))
    }

    /// Model contract validation, unless profiling skips it.
    fn contracts(
        &self,
        project: &Bound<'py, PyAny>,
        dialect: &Bound<'py, PyAny>,
    ) -> PyResult<ContractPhase<'py>> {
        let py: Python<'py> = self.py;
        let thread_time: Bound<'py, PyAny> = imported(py, "time", "thread_time")?;
        let started: Instant = Instant::now();
        let cpu_started: f64 = thread_time.call0()?.extract()?;
        let skip: bool = self
            .options
            .profile_flags
            .getattr("skip_contracts")?
            .is_truthy()?;
        let result: Bound<'py, PyAny> = if skip {
            call_with(
                &imported(py, CONTRACT_MODELS_MODULE, "ContractValidationResult")?,
                &[("diagnostics", PyTuple::empty(py).into_any())],
            )?
        } else {
            self.status.start("Validating model contracts...")?;
            call_with(
                &imported(py, CONTRACTS_MODULE, "evaluate_model_contracts")?,
                &[("project", project.clone()), ("dialect", dialect.clone())],
            )?
        };
        let wall_ms: u64 = elapsed_ms(started);
        let cpu_ended: f64 = thread_time.call0()?.extract()?;
        let cpu_ms: i64 = ((cpu_ended - cpu_started) * 1000.0) as i64;
        if !skip {
            self.status.complete(&format!(
                "Validated model contracts. ({}s)",
                seconds(wall_ms)
            ))?;
        }
        Ok(ContractPhase {
            result,
            wall_ms,
            cpu_ms,
        })
    }

    /// Stage artifacts when the compile is clean, then run the built-in and custom rules.
    fn rules(
        &self,
        (graph, discovered, adapter): (&Bound<'py, PyAny>, &Bound<'py, PyAny>, &Bound<'py, PyAny>),
        (core_diagnostics, selected_keys): (&Bound<'py, PyTuple>, &Bound<'py, PyAny>),
        lint_dialect: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let py: Python<'py> = self.py;
        let options: &AnalysisOptions<'py> = self.options;
        let project_dir: &Bound<'py, PyAny> = &options.project_dir;
        let rules_config: Bound<'py, PyAny> =
            load_rules_config(py, project_dir.extract()?)?.into_bound(py);
        if !options.prepared_artifacts.is_none() && !any_error(core_diagnostics.as_any())? {
            let target_dir: Bound<'py, PyAny> =
                project_dir.call_method1("__truediv__", (TARGET_DIRECTORY,))?;
            let stage_artifacts: bool = rules_config.getattr("select")?.is_truthy()?;
            call_with(
                &options.prepared_artifacts.getattr("start")?,
                &[
                    ("project", graph.getattr("project")?),
                    ("adapter", adapter.clone()),
                    ("target_dir", target_dir),
                    (
                        "stage_artifacts",
                        PyBool::new(py, stage_artifacts).to_owned().into_any(),
                    ),
                ],
            )?;
        }
        self.status
            .start("Evaluating built-in and custom rules...")?;
        let monotonic: Bound<'py, PyAny> = imported(py, "time", "monotonic")?;
        let started: f64 = monotonic.call0()?.extract()?;
        let selected: Bound<'py, PyAny> = if self.select.is_truthy()? || self.exclude.is_truthy()? {
            selected_keys.clone()
        } else {
            py.None().into_bound(py)
        };
        let result: Bound<'py, PyAny> = call_with(
            &imported(py, RULE_THREADS_MODULE, "evaluate_rules")?,
            &[
                ("graph", graph.clone()),
                ("discovered_inputs", discovered.clone()),
                ("config", rules_config),
                ("project_dir", project_dir.clone()),
                ("dialect", lint_dialect.clone()),
                ("selected_keys", selected),
                ("prepared_sql", self.early_lint.getattr("preparation")?),
                (
                    "expansion_reuse",
                    self.early_lint.getattr("expansion_reuse")?,
                ),
                ("no_sql_analysis", options.no_sql_validation.clone()),
            ],
        )?;
        let ended: f64 = monotonic.call0()?.extract()?;
        let progress: String = rules_progress(ended - started, &result, false)?;
        self.status.complete(&progress)?;
        Ok(result)
    }
}

/// The core diagnostics followed by one rule-phase error per rule finding.
fn with_rule_diagnostics<'py>(
    py: Python<'py>,
    core: &Bound<'py, PyTuple>,
    rules_result: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let diagnostic_class: Bound<'py, PyAny> =
        imported(py, COMPILE_MODELS_MODULE, "CompilerDiagnostic")?;
    let phase: Bound<'py, PyAny> =
        imported(py, NATIVE_RECORDS_MODULE, "DiagnosticPhase")?.getattr("RULE")?;
    let severity: Bound<'py, PyAny> =
        imported(py, NATIVE_RECORDS_MODULE, "DiagnosticSeverity")?.getattr("ERROR")?;
    let fix_note: Bound<'py, PyAny> = PyString::new(py, RULE_FIX_AVAILABLE_NOTE).into_any();
    let mut diagnostics: Vec<Bound<'py, PyAny>> = core.iter().collect();
    for fault in rules_result.getattr("findings")?.try_iter()? {
        let fault: Bound<'py, PyAny> = fault?;
        let notes: Bound<'py, PyTuple> = if fault.getattr("fixable")?.is_truthy()? {
            PyTuple::new(py, [fix_note.clone()])?
        } else {
            PyTuple::empty(py)
        };
        diagnostics.push(call_with(
            &diagnostic_class,
            &[
                ("phase", phase.clone()),
                ("severity", severity.clone()),
                ("code", fault.getattr("code")?),
                ("message", fault.getattr("message")?),
                ("path", fault.getattr("path")?),
                ("line", fault.getattr("line")?),
                ("column", fault.getattr("column")?),
                ("help", fault.getattr("remediation")?),
                ("notes", notes.into_any()),
                ("affected_rules", fault.getattr("affected_rules")?),
            ],
        )?);
    }
    PyTuple::new(py, diagnostics)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(analyze_compile_project, module)?)
}
