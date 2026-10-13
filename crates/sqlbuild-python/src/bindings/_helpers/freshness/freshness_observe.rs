//! Observe the current freshness of selected sources and compare it with previous state.

use std::collections::{HashMap, HashSet};

use pyo3::exceptions::{PyException, PyValueError};
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_core::freshness_text::main::freshness_json::freshness_json;

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use sqlbuild_core::freshness_text::main::freshness_status::freshness_status;
use sqlbuild_core::freshness_text::models::{
    FreshnessSourceResult, FreshnessStatus, StateComparison,
};

const FRESHNESS_PACKAGE: &str = "sqlbuild.compiler.source_freshness.main";
const NATIVE: &str = "_native";
const NATIVE_MODULE: &str = "sqlbuild._native";
const FRESHNESS_MODELS: &str = "sqlbuild.compiler.source_freshness.models";
const CONTRACT_MODELS: &str = "sqlbuild.spec.contracts.models";
const CONTRACT_TYPES: &str = "sqlbuild.spec.contracts.types";
const RUN_SCOPE_MODULE: &str = "sqlbuild.runtime.observability.main.run_scope";
const ADAPTER_STRATEGY: &str = "adapter";
const UNAVAILABLE_REASON: &str = "unavailable";
const OBSERVATION_RUN_ID: &str = "freshness";
const NO_CONFIG_MESSAGE: &str = "no freshness config and adapter metadata unavailable";
const MISSING_STATE_MESSAGE: &str = "previous source freshness state missing";
const NOT_RETURNED_MESSAGE: &str = "freshness metadata was not returned";

/// The adapter, connection and observation time every source is observed with.
pub(crate) struct Observer<'py> {
    pub(crate) adapter: Bound<'py, PyAny>,
    pub(crate) connection: Bound<'py, PyAny>,
    pub(crate) observed_at: Bound<'py, PyAny>,
}

/// Previous state records by identity; absent means no comparison.
pub(crate) struct PreviousState<'py> {
    pub(crate) by_identity: Option<Bound<'py, PyAny>>,
}

fn freshness_function<'py>(
    py: Python<'py>,
    (module, name): (&str, &str),
) -> PyResult<Bound<'py, PyAny>> {
    if module == NATIVE {
        return py.import(NATIVE_MODULE)?.getattr(name);
    }
    py.import(format!("{FRESHNESS_PACKAGE}.{module}"))?
        .getattr(name)
}

fn optional_text(value: Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    Ok(Some(value.str()?.extract()?))
}

/// `str(exc)` of an `Exception`, or the error itself for anything else.
fn exception_message(py: Python<'_>, error: PyErr) -> PyResult<String> {
    if !error.is_instance_of::<PyException>(py) {
        return Err(error);
    }
    error.value(py).str()?.extract()
}

fn target_result(
    source: &Bound<'_, PyAny>,
    (name, status): (&str, FreshnessStatus),
    message: Option<String>,
) -> PyResult<FreshnessSourceResult> {
    let mut result: FreshnessSourceResult = FreshnessSourceResult::new(name, status);
    result.target_database = optional_text(source.getattr("database")?)?;
    result.target_schema = optional_text(source.getattr("schema")?)?;
    result.target_name = optional_text(source.getattr("table")?)?;
    result.message = message;
    Ok(result)
}

fn strategy(source: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    let freshness: Bound<'_, PyAny> = source.getattr("freshness")?;
    if freshness.is_none() {
        return Ok(None);
    }
    optional_text(freshness.getattr("strategy")?)
}

/// The source as observed: itself with freshness config, an adapter-metadata copy, or none.
fn observation_source<'py>(
    adapter: &Bound<'py, PyAny>,
    source: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let py: Python<'py> = source.py();
    if !source.getattr("freshness")?.is_none() {
        return Ok(Some(source.clone()));
    }
    if !source.getattr("expression")?.is_none()
        || source.getattr("table")?.is_none()
        || !adapter
            .call_method0("supports_table_freshness_metadata")?
            .is_truthy()?
    {
        return Ok(None);
    }
    let config: Bound<'py, PyDict> = PyDict::new(py);
    config.set_item(
        "strategy",
        py.import(CONTRACT_TYPES)?
            .getattr("SourceFreshnessStrategy")?
            .getattr("ADAPTER")?,
    )?;
    let changes: Bound<'py, PyDict> = PyDict::new(py);
    changes.set_item(
        "freshness",
        py.import(CONTRACT_MODELS)?
            .getattr("SourceFreshnessConfig")?
            .call((), Some(&config))?,
    )?;
    Ok(Some(
        py.import("dataclasses")?
            .getattr("replace")?
            .call((source,), Some(&changes))?,
    ))
}

/// The state record of one observation, with its normalized version and hash.
fn record<'py>(
    observation: &Bound<'py, PyAny>,
    source: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = observation.py();
    let normalize: Bound<'py, PyDict> = PyDict::new(py);
    normalize.set_item("value", observation.getattr("data_version")?)?;
    normalize.set_item("value_kind", observation.getattr("value_kind")?)?;
    let data_version: Bound<'py, PyAny> =
        freshness_function(py, (NATIVE, "normalize_source_freshness_data_version"))?
            .call((), Some(&normalize))?;
    let hash: Bound<'py, PyDict> = PyDict::new(py);
    hash.set_item("source_name", observation.getattr("source_name")?)?;
    hash.set_item("strategy", observation.getattr("strategy")?)?;
    hash.set_item("value_kind", observation.getattr("value_kind")?)?;
    hash.set_item("data_version", &data_version)?;
    let data_version_hash: Bound<'py, PyAny> =
        freshness_function(py, (NATIVE, "source_freshness_data_version_hash"))?
            .call((), Some(&hash))?;
    let fields: Bound<'py, PyDict> = PyDict::new(py);
    fields.set_item("source_name", observation.getattr("source_name")?)?;
    fields.set_item("target_database", source.getattr("database")?)?;
    fields.set_item("target_schema", source.getattr("schema")?)?;
    fields.set_item("target_name", source.getattr("table")?)?;
    fields.set_item("run_id", OBSERVATION_RUN_ID)?;
    fields.set_item(
        "strategy",
        observation.getattr("strategy")?.getattr("value")?,
    )?;
    fields.set_item(
        "value_kind",
        observation.getattr("value_kind")?.getattr("value")?,
    )?;
    fields.set_item("data_version", &data_version)?;
    fields.set_item("data_version_hash", data_version_hash)?;
    fields.set_item("observed_at", observation.getattr("observed_at")?)?;
    py.import(FRESHNESS_MODELS)?
        .getattr("SourceFreshnessRecord")?
        .call((), Some(&fields))
}

fn previous_record<'py>(
    state: &PreviousState<'py>,
    record: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let Some(lookup) = &state.by_identity else {
        return Ok(None);
    };
    let found: Bound<'py, PyAny> = lookup.call_method1("get", (record.getattr("identity")?,))?;
    Ok(found.is_truthy()?.then_some(found))
}

/// The command result of one successful observation.
fn observed_result(
    (name, source, observation): (&str, &Bound<'_, PyAny>, &Bound<'_, PyAny>),
    state: &PreviousState<'_>,
) -> PyResult<FreshnessSourceResult> {
    let py: Python<'_> = source.py();
    let current: Bound<'_, PyAny> = record(observation, source)?;
    let freshness: Bound<'_, PyAny> = source.getattr("freshness")?;
    let (lag_tolerance, policy) = if freshness.is_none() {
        (py.None().into_bound(py), py.None().into_bound(py))
    } else {
        (
            freshness.getattr("lag_tolerance")?,
            freshness.getattr("age_policy")?,
        )
    };
    let age: Bound<'_, PyDict> = PyDict::new(py);
    age.set_item("policy", policy)?;
    age.set_item("data_version", observation.getattr("data_version")?)?;
    age.set_item("observed_at", observation.getattr("observed_at")?)?;
    let age_status: Bound<'_, PyAny> =
        freshness_function(py, (NATIVE, "evaluate_source_freshness_age_policy"))?
            .call((), Some(&age))?;
    let previous: Option<Bound<'_, PyAny>> = previous_record(state, &current)?;
    let comparison: StateComparison = match &previous {
        None if state.by_identity.is_some() => StateComparison::Missing,
        None => StateComparison::NotCompared,
        Some(previous) => {
            let options: Bound<'_, PyDict> = PyDict::new(py);
            options.set_item("previous_record", previous)?;
            options.set_item("current_record", &current)?;
            options.set_item("lag_tolerance", &lag_tolerance)?;
            let equivalent: bool =
                freshness_function(py, (NATIVE, "source_freshness_records_equivalent"))?
                    .call((), Some(&options))?
                    .is_truthy()?;
            if equivalent {
                StateComparison::Equivalent {
                    same_hash: previous
                        .getattr("data_version_hash")?
                        .eq(current.getattr("data_version_hash")?)?,
                }
            } else {
                StateComparison::Different
            }
        }
    };
    let mut result: FreshnessSourceResult =
        FreshnessSourceResult::new(name, freshness_status(comparison));
    result.strategy = optional_text(current.getattr("strategy")?)?;
    result.value_kind = optional_text(current.getattr("value_kind")?)?;
    result.current_data_version = optional_text(current.getattr("data_version")?)?;
    result.previous_data_version = match &previous {
        Some(previous) => optional_text(previous.getattr("data_version")?)?,
        None => None,
    };
    result.lag_tolerance = optional_text(lag_tolerance)?;
    result.target_database = optional_text(current.getattr("target_database")?)?;
    result.target_schema = optional_text(current.getattr("target_schema")?)?;
    result.target_name = optional_text(current.getattr("target_name")?)?;
    if comparison == StateComparison::Missing {
        result.message = Some(MISSING_STATE_MESSAGE.to_owned());
    }
    result.age_status = if age_status.is_none() {
        None
    } else {
        Some(age_status.getattr("value")?.extract()?)
    };
    Ok(result)
}

/// Adapter-strategy observations in one batch, or the message of the batch failure.
fn adapter_batch<'py>(
    observer: &Observer<'py>,
    sources: &[Bound<'py, PyAny>],
) -> PyResult<Result<Bound<'py, PyAny>, String>> {
    let py: Python<'py> = observer.adapter.py();
    let batch_class: Bound<'py, PyAny> = py
        .import(FRESHNESS_MODELS)?
        .getattr("AdapterSourceFreshnessBatch")?;
    if sources.is_empty() {
        return Ok(Ok(batch_class.call0()?));
    }
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("adapter", &observer.adapter)?;
    options.set_item("connection", &observer.connection)?;
    options.set_item("sources", PyTuple::new(py, sources)?)?;
    options.set_item("observed_at", &observer.observed_at)?;
    match freshness_function(
        py,
        ("adapter_observation", "observe_adapter_sources_freshness"),
    )?
    .call((), Some(&options))
    {
        Ok(batch) => Ok(Ok(batch)),
        Err(error) => Ok(Err(exception_message(py, error)?)),
    }
}

/// One adapter-strategy source's observation, or its unknown or error result.
fn adapter_observation<'py>(
    batch: &Result<Bound<'py, PyAny>, String>,
    (name, source): (&str, &Bound<'py, PyAny>),
) -> PyResult<Result<Bound<'py, PyAny>, FreshnessSourceResult>> {
    let batch: &Bound<'py, PyAny> = match batch {
        Ok(batch) => batch,
        Err(message) => {
            return Ok(Err(target_result(
                source,
                (name, FreshnessStatus::Error),
                Some(message.clone()),
            )?));
        }
    };
    let unknown: Bound<'py, PyAny> = batch.getattr("unknown")?.call_method1("get", (name,))?;
    if !unknown.is_none() {
        let reason: String = unknown.getattr("reason")?.str()?.extract()?;
        let status: FreshnessStatus = if reason == UNAVAILABLE_REASON {
            FreshnessStatus::Unknown
        } else {
            FreshnessStatus::Error
        };
        return Ok(Err(target_result(
            source,
            (name, status),
            optional_text(unknown.getattr("message")?)?,
        )?));
    }
    let observation: Bound<'py, PyAny> = batch
        .getattr("observations")?
        .call_method1("get", (name,))?;
    if observation.is_none() {
        return Ok(Err(target_result(
            source,
            (name, FreshnessStatus::Error),
            Some(NOT_RETURNED_MESSAGE.to_owned()),
        )?));
    }
    Ok(Ok(observation))
}

/// One configured-strategy source's observation, or its error result.
fn configured_observation<'py>(
    observer: &Observer<'py>,
    (name, source): (&str, &Bound<'py, PyAny>),
) -> PyResult<Result<Bound<'py, PyAny>, FreshnessSourceResult>> {
    let py: Python<'py> = source.py();
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("adapter", &observer.adapter)?;
    options.set_item("connection", &observer.connection)?;
    options.set_item("source", source)?;
    options.set_item("observed_at", &observer.observed_at)?;
    match freshness_function(py, ("observation", "observe_configured_source_freshness"))?
        .call((), Some(&options))
    {
        Ok(observation) => Ok(Ok(observation)),
        Err(error) => Ok(Err(target_result(
            source,
            (name, FreshnessStatus::Error),
            Some(exception_message(py, error)?),
        )?)),
    }
}

fn observe_sources(
    observer: &Observer<'_>,
    sources: &[Bound<'_, PyAny>],
    state: &PreviousState<'_>,
) -> PyResult<Vec<FreshnessSourceResult>> {
    let mut results: Vec<FreshnessSourceResult> = Vec::new();
    let mut observed: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
    let mut positions: HashMap<String, usize> = HashMap::new();
    let mut adapter_sources: Vec<Bound<'_, PyAny>> = Vec::new();
    for source in sources {
        let name: String = source.getattr("name")?.extract()?;
        let Some(observed_source) = observation_source(&observer.adapter, source)? else {
            results.push(target_result(
                source,
                (&name, FreshnessStatus::Unknown),
                Some(NO_CONFIG_MESSAGE.to_owned()),
            )?);
            continue;
        };
        if strategy(&observed_source)?.as_deref() == Some(ADAPTER_STRATEGY) {
            adapter_sources.push(observed_source.clone());
        }
        match positions.get(&name) {
            Some(&position) => observed[position].1 = observed_source,
            None => {
                positions.insert(name.clone(), observed.len());
                observed.push((name, observed_source));
            }
        }
    }
    let batch = adapter_batch(observer, &adapter_sources)?;
    for (name, source) in &observed {
        let observation = if strategy(source)?.as_deref() == Some(ADAPTER_STRATEGY) {
            adapter_observation(&batch, (name, source))?
        } else {
            configured_observation(observer, (name, source))?
        };
        match observation {
            Ok(observation) => results.push(observed_result((name, source, &observation), state)?),
            Err(result) => results.push(result),
        }
    }
    results.sort_by(|left, right| left.name.cmp(&right.name));
    Ok(results)
}

/// Observe the selected sources inside the run's observability scope.
pub(crate) fn observe_freshness(
    observer: &Observer<'_>,
    (sources, select, exclude): (&Bound<'_, PyAny>, &[String], &[String]),
    (run_id, state): (Option<String>, &PreviousState<'_>),
) -> PyResult<Vec<FreshnessSourceResult>> {
    let py: Python<'_> = observer.adapter.py();
    let selected: HashSet<&str> = select.iter().map(String::as_str).collect();
    let excluded: HashSet<&str> = exclude.iter().map(String::as_str).collect();
    let mut chosen: Vec<Bound<'_, PyAny>> = Vec::new();
    for source in sources.try_iter()? {
        let source: Bound<'_, PyAny> = source?;
        let name: String = source.getattr("name")?.extract()?;
        if (selected.is_empty() || selected.contains(name.as_str()))
            && !excluded.contains(name.as_str())
        {
            chosen.push(source);
        }
    }
    let Some(run_id) = run_id else {
        return observe_sources(observer, &chosen, state);
    };
    let scope: Bound<'_, PyAny> = py
        .import(RUN_SCOPE_MODULE)?
        .getattr("run_scope")?
        .call1((run_id,))?;
    scope.call_method0("__enter__")?;
    match observe_sources(observer, &chosen, state) {
        Ok(results) => {
            scope.call_method1("__exit__", (py.None(), py.None(), py.None()))?;
            Ok(results)
        }
        Err(error) => {
            scope.call_method1(
                "__exit__",
                (error.get_type(py), error.value(py), error.traceback(py)),
            )?;
            Err(error)
        }
    }
}

/// Observe source freshness and return the `sqb freshness --json` payload.
#[pyfunction]
#[pyo3(signature = (**options))]
fn observe_source_freshness_json(
    py: Python<'_>,
    options: Option<Bound<'_, PyDict>>,
) -> PyResult<String> {
    let arguments: KeywordArguments<'_> = KeywordArguments::read(
        py,
        "observe_source_freshness_json",
        options,
        (
            &["adapter", "connection", "sources", "observed_at"],
            &["select", "exclude", "run_id", "previous_records"],
        ),
    )?;
    let names = |name: &str| -> PyResult<Vec<String>> {
        let value: Bound<'_, PyAny> = arguments.value(name)?;
        if value.is_none() {
            return Ok(Vec::new());
        }
        value.extract()
    };
    let observer: Observer<'_> = Observer {
        adapter: arguments.value("adapter")?,
        connection: arguments.value("connection")?,
        observed_at: arguments.value("observed_at")?,
    };
    let previous: Bound<'_, PyAny> = arguments.value("previous_records")?;
    let state: PreviousState<'_> = PreviousState {
        by_identity: (!previous.is_none()).then_some(previous),
    };
    let results: Vec<FreshnessSourceResult> = observe_freshness(
        &observer,
        (
            &arguments.value("sources")?,
            &names("select")?,
            &names("exclude")?,
        ),
        (arguments.value("run_id")?.extract()?, &state),
    )?;
    freshness_json(&results).map_err(|error| PyValueError::new_err(format!("{error:?}")))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(observe_source_freshness_json, module)?)?;
    Ok(())
}
