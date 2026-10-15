//! Speculative SQL checks started once compile inputs are ready, and the lint settings they use.

use std::path::PathBuf;
use std::time::Instant;

use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyRefMut, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyList, PyTuple};
use pyo3::{IntoPyObject, IntoPyObjectExt, pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_rules::rule_cache::main::rules_bulk_cache_path::rules_bulk_cache_path;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};

const NATIVE_MODULE: &str = "sqlbuild._native";
const RULE_THREADS_MODULE: &str = "sqlbuild._native";
const RULES_MODELS_MODULE: &str = "sqlbuild.rule_engine.models";
const LINT_MODELS_MODULE: &str = "sqlbuild._native";
/// The lint thresholds used when the project leaves them unset.
const DEFAULT_MAX_LITERAL_LENGTH: i64 = 100;
const DEFAULT_MAX_RANKING_ORDER_BY: i64 = 5;
const FUTURES_MODULE: &str = "concurrent.futures";
const THREADING_MODULE: &str = "threading";
const LINT_THREAD_PREFIX: &str = "sqlbuild-lint";
const SQL_RULES_CACHE_FILE: &str = "sql.json";

/// The SQL rule result cache file of `project_dir`.
pub(crate) fn sql_rule_cache_path<'py>(
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let root: PathBuf = project_dir.extract()?;
    Ok(rules_bulk_cache_path(&root, SQL_RULES_CACHE_FILE)
        .into_pyobject(project_dir.py())?
        .into_any())
}

/// The native SQL lint configuration that SQL rules run with.
pub(crate) fn sql_lint_config<'py>(
    dialect: &Bound<'py, PyAny>,
    codes: &[String],
    thresholds: &Bound<'py, PyAny>,
    (relation_keys, allow_suppressions): (Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = dialect.py();
    let threshold = |key: &str, default: i64| -> PyResult<Bound<'py, PyAny>> {
        thresholds.call_method1("get", (key, default))
    };
    call_with(
        &imported(py, LINT_MODELS_MODULE, "LintConfig")?,
        &[
            ("dialect", dialect.clone()),
            ("enabled_native_rules", PyTuple::new(py, codes)?.into_any()),
            ("header_rules_enabled", false.into_bound_py_any(py)?),
            (
                "max_literal_length",
                threshold("max_literal_length", DEFAULT_MAX_LITERAL_LENGTH)?,
            ),
            (
                "max_ranking_order_by",
                threshold("max_ranking_order_by", DEFAULT_MAX_RANKING_ORDER_BY)?,
            ),
            ("relation_keys", relation_keys),
            ("allow_suppressions", allow_suppressions),
        ],
    )
}

/// The project, SQL rule codes and lint settings early SQL lint runs with, if it should run.
#[pyfunction]
#[pyo3(signature = (*, inputs, dialect))]
fn sql_lint_preparation<'py>(
    inputs: &Bound<'py, PyAny>,
    dialect: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyTuple>>> {
    let py: Python<'py> = inputs.py();
    let native = |name: &str| imported(py, NATIVE_MODULE, name);
    let project_dir: Bound<'py, PyAny> = inputs
        .getattr("discovered_inputs")?
        .getattr("project_dir")?;
    if project_dir.is_none() {
        return Ok(None);
    }
    for diagnostic in inputs.getattr("diagnostics")?.try_iter()? {
        if diagnostic?.getattr("is_error")?.is_truthy()? {
            return Ok(None);
        }
    }
    let config: Bound<'py, PyAny> = call_with(
        &native("valid_rules_config")?,
        &[("project_dir", project_dir.clone())],
    )?;
    if config.is_none() || !config.getattr("select")?.is_truthy()? {
        return Ok(None);
    }
    if config.getattr("cache")?.getattr("enabled")?.is_truthy()?
        && call_with(
            &native("load_sql_rule_cache")?,
            &[("path", sql_rule_cache_path(&project_dir)?)],
        )?
        .is_truthy()?
    {
        return Ok(None);
    }
    let codes: Vec<String> = call_with(
        &native("selected_sql_rule_codes")?,
        &[
            (
                "select",
                PyList::new(
                    py,
                    config
                        .getattr("select")?
                        .try_iter()?
                        .collect::<PyResult<Vec<_>>>()?,
                )?
                .into_any(),
            ),
            (
                "ignore",
                PyList::new(
                    py,
                    config
                        .getattr("ignore")?
                        .try_iter()?
                        .collect::<PyResult<Vec<_>>>()?,
                )?
                .into_any(),
            ),
        ],
    )?
    .extract()?;
    if codes.is_empty() {
        return Ok(None);
    }
    let mut model_rows: Vec<Bound<'py, PyAny>> = Vec::new();
    for model in inputs.getattr("model_inputs")?.try_iter()? {
        model_rows.push(model?.getattr("relation_key_row")?);
    }
    let mut seeds: Vec<Bound<'py, PyAny>> = Vec::new();
    for seed in inputs.getattr("seed_inputs")?.try_iter()? {
        seeds.push(seed?.getattr("schema_entry")?);
    }
    let mut sources: Vec<Bound<'py, PyAny>> = Vec::new();
    for source in inputs.getattr("source_inputs")?.try_iter()? {
        sources.push(source?.getattr("source_entry")?);
    }
    let relation_keys: Bound<'py, PyAny> = call_with(
        &native("declared_relation_keys")?,
        &[
            ("model_rows", PyList::new(py, model_rows)?.into_any()),
            ("seeds", PyList::new(py, seeds)?.into_any()),
            ("sources", PyList::new(py, sources)?.into_any()),
        ],
    )?;
    let lint_config: Bound<'py, PyAny> = sql_lint_config(
        dialect,
        &codes,
        &config.getattr("thresholds")?,
        (relation_keys, config.getattr("allow_exceptions")?),
    )?;
    Ok(Some(PyTuple::new(
        py,
        [
            project_dir,
            PyTuple::new(py, codes)?.into_any(),
            lint_config,
        ],
    )?))
}

/// Each model's compile expansion for early lint, whole when the compile handed one over.
#[pyfunction]
fn early_lint_expansions<'py>(model_inputs: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let expansions: Bound<'py, PyDict> = PyDict::new(model_inputs.py());
    for model in model_inputs.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        let mut expansion: Bound<'py, PyAny> = model.getattr("lint_expansion")?;
        if !expansion.is_truthy()? {
            expansion = model.getattr("sql_expansion")?;
        }
        if !expansion.is_none() {
            expansions.set_item(
                model.getattr("model_file")?.getattr("file_path")?,
                expansion,
            )?;
        }
    }
    Ok(expansions)
}

/// Own speculative SQL checks for one compilation invocation.
#[pyclass(module = "sqlbuild._native")]
pub(crate) struct EarlySqlLint {
    #[pyo3(get)]
    enabled: bool,
    #[pyo3(get)]
    preparation: Py<PyAny>,
    #[pyo3(get)]
    expansion_reuse: Py<PyAny>,
    stop_requested: Py<PyAny>,
    executor: Py<PyAny>,
}

impl EarlySqlLint {
    /// A manager that starts speculative checks only when `enabled`.
    pub(crate) fn new(py: Python<'_>, enabled: bool) -> PyResult<Self> {
        let executor: Bound<'_, PyAny> = call_with(
            &imported(py, FUTURES_MODULE, "ThreadPoolExecutor")?,
            &[
                ("max_workers", 1.into_bound_py_any(py)?),
                (
                    "thread_name_prefix",
                    LINT_THREAD_PREFIX.into_bound_py_any(py)?,
                ),
            ],
        )?;
        Ok(Self {
            enabled,
            preparation: py.None(),
            expansion_reuse: py.None(),
            stop_requested: imported(py, THREADING_MODULE, "Event")?.call0()?.unbind(),
            executor: executor.unbind(),
        })
    }
}

#[pymethods]
impl EarlySqlLint {
    #[new]
    #[pyo3(signature = (*, enabled))]
    fn py_new(py: Python<'_>, enabled: bool) -> PyResult<Self> {
        Self::new(py, enabled)
    }

    fn __enter__(slf: PyRefMut<'_, Self>) -> PyRefMut<'_, Self> {
        slf
    }

    #[pyo3(signature = (*_exception))]
    fn __exit__(&self, py: Python<'_>, _exception: &Bound<'_, PyTuple>) -> PyResult<()> {
        let _ = self.stop(py)?;
        Ok(())
    }

    /// Start early SQL lint for `inputs` when enabled and the project selects SQL rules.
    #[pyo3(signature = (*, inputs, dialect))]
    fn start(
        mut slf: PyRefMut<'_, Self>,
        inputs: &Bound<'_, PyAny>,
        dialect: &Bound<'_, PyAny>,
    ) -> PyResult<()> {
        if !slf.enabled {
            return Ok(());
        }
        let py: Python<'_> = inputs.py();
        let preparation: Bound<'_, PyAny> = call_with(
            &imported(py, RULE_THREADS_MODULE, "prepare_sql_rules")?,
            &[
                ("inputs", inputs.clone()),
                ("executor", slf.executor.bind(py).clone()),
                ("dialect", dialect.clone()),
                ("stop", slf.stop_requested.bind(py).clone()),
            ],
        )?;
        let declaration_scope: Bound<'_, PyAny> = inputs.getattr("declaration_scope")?;
        let expansion_reuse: Bound<'_, PyAny> = if declaration_scope.is_none() {
            declaration_scope
        } else {
            call_with(
                &imported(py, RULES_MODELS_MODULE, "SqlExpansionReuse")?,
                &[
                    ("discovered_inputs", inputs.getattr("discovered_inputs")?),
                    ("declaration_scope", declaration_scope),
                ],
            )?
        };
        slf.preparation = preparation.unbind();
        slf.expansion_reuse = expansion_reuse.unbind();
        Ok(())
    }

    /// Abandon unconsumed speculative work and return the milliseconds spent joining it.
    fn stop(&self, py: Python<'_>) -> PyResult<u64> {
        let started: Instant = Instant::now();
        let _ = self.stop_requested.bind(py).call_method0("set")?;
        let _ = self.executor.bind(py).call_method(
            "shutdown",
            (),
            Some(&keywords(
                py,
                &[
                    ("wait", true.into_bound_py_any(py)?),
                    ("cancel_futures", true.into_bound_py_any(py)?),
                ],
            )?),
        )?;
        Ok(u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX))
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<EarlySqlLint>()?;
    module.add_function(wrap_pyfunction!(sql_lint_preparation, module)?)?;
    module.add_function(wrap_pyfunction!(early_lint_expansions, module)?)?;
    Ok(())
}
