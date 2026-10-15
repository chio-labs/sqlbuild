//! Planning-time source freshness: observe, compare with latest state and map downstream impact.

use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PySet, PySetMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_state::freshness::main::configuration_error::configuration_error;

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::freshness::observation::{
    Observer, observation_record, observation_source, observe_adapter_batch, observe_configured,
    strategy, unknown,
};
use crate::bindings::_helpers::freshness::state_io::{StateRead, read_latest};
use crate::bindings::_helpers::freshness::support::{
    ADAPTER_EXCEPTIONS, EXCEPTIONS_MODULE, FRESHNESS_MODELS, FRESHNESS_TYPES, OBSERVATION_ERROR,
    text,
};
use crate::bindings::_helpers::planner_identity::graph::build_downstream_model_name_closure;
use crate::bindings::_helpers::state_rows::freshness::{age_policy, equivalent};

const ADAPTER_STRATEGY: &str = "adapter";
const COMPILE_MODELS: &str = "sqlbuild.compiler.compile.models";
const COMPILE_TYPES: &str = "sqlbuild.compiler.compile.types";
const NO_CONFIG_MESSAGE: &str = "no freshness config and adapter metadata unavailable";

/// The message of an `AdapterUserError` or a source freshness observation error, if it is one.
fn handled_message<'py>(py: Python<'py>, error: &PyErr) -> PyResult<Option<Bound<'py, PyAny>>> {
    let value: Bound<'py, PyAny> = error.value(py).clone().into_any();
    if value.is_instance(&imported(py, ADAPTER_EXCEPTIONS, "AdapterUserError")?)? {
        return value.getattr("message").map(Some);
    }
    if value.is_instance(&imported(py, EXCEPTIONS_MODULE, OBSERVATION_ERROR)?)? {
        return Ok(Some(value.str()?.into_any()));
    }
    Ok(None)
}

fn freshness_strategy_is_adapter(source: &Bound<'_, PyAny>) -> PyResult<bool> {
    Ok(strategy(source)?.as_deref() == Some(ADAPTER_STRATEGY))
}

/// Latest previous records by identity across the state schemas, newest observation winning.
fn previous_records<'py>(
    arguments: &KeywordArguments<'py>,
    (adapter, connection): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    source_names: Option<&[String]>,
) -> PyResult<Bound<'py, PyDict>> {
    let py: Python<'py> = adapter.py();
    let read: StateRead<'py> = StateRead {
        connection: connection.clone(),
        execute: adapter.getattr("execute")?,
        render_qualified_name: arguments.value("render_qualified_name")?,
        render_read_latest_sql: adapter.getattr("render_read_latest_source_freshness_sql")?,
    };
    let database: Bound<'py, PyAny> = arguments.value("state_database")?;
    let exists_by_schema: Bound<'py, PyAny> = arguments.value("state_table_exists_by_schema")?;
    let merged: Bound<'py, PyDict> = PyDict::new(py);
    for schema in arguments.value("state_schemas")?.try_iter()? {
        let schema: Bound<'py, PyAny> = schema?;
        let exists: bool = exists_by_schema
            .call_method1("get", (&schema, false))?
            .is_truthy()?;
        let previous: Bound<'py, PyAny> =
            read_latest(&read, (&database, &schema), exists, source_names)?;
        for (identity, candidate) in previous.getattr("records")?.downcast::<PyDict>()?.iter() {
            let replace: bool = match merged.get_item(&identity)? {
                None => true,
                Some(current) => candidate
                    .getattr("observed_at")?
                    .gt(current.getattr("observed_at")?)?,
            };
            if replace {
                merged.set_item(identity, candidate)?;
            }
        }
    }
    Ok(merged)
}

/// Records sorted by `str(record.identity)`, stably.
fn sorted_by_identity<'py>(
    records: impl Iterator<Item = Bound<'py, PyAny>>,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut keyed: Vec<(String, Bound<'py, PyAny>)> = records
        .map(|record| Ok((record.getattr("identity")?.str()?.extract()?, record)))
        .collect::<PyResult<_>>()?;
    keyed.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(keyed.into_iter().map(|(_, record)| record).collect())
}

fn sorted_dict<'py>(py: Python<'py>, items: &Bound<'py, PyDict>) -> PyResult<Bound<'py, PyDict>> {
    let mut keyed: Vec<(String, Bound<'py, PyAny>)> = items
        .iter()
        .map(|(name, value)| Ok((name.extract()?, value)))
        .collect::<PyResult<_>>()?;
    keyed.sort_by(|left, right| left.0.cmp(&right.0));
    let sorted: Bound<'py, PyDict> = PyDict::new(py);
    for (name, value) in keyed {
        sorted.set_item(name, value)?;
    }
    Ok(sorted)
}

/// The adapter batch, or every source unknown with the batch failure's message.
fn adapter_batch<'py>(
    observer: &Observer<'py>,
    sources: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = observer.adapter.py();
    let error: PyErr = match observe_adapter_batch(observer, sources) {
        Ok(batch) => return Ok(batch),
        Err(error) => error,
    };
    let Some(message) = handled_message(py, &error)? else {
        return Err(error);
    };
    let unknown_sources: Bound<'py, PyDict> = PyDict::new(py);
    for source in sources {
        let name: Bound<'py, PyAny> = source.getattr("name")?;
        unknown_sources.set_item(&name, unknown(&name, ("ERROR", message.clone()))?)?;
    }
    call_with(
        &imported(py, FRESHNESS_MODELS, "AdapterSourceFreshnessBatch")?,
        &[("unknown", unknown_sources.into_any())],
    )
}

/// Observe direct source freshness and compare it to latest append-only state.
#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn build_direct_source_freshness_planning_result<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> = KeywordArguments::read(
        py,
        "build_direct_source_freshness_planning_result",
        options,
        (
            &[
                "adapter",
                "connection",
                "sources",
                "state_database",
                "state_schemas",
                "observed_at",
                "run_id",
                "render_qualified_name",
                "state_table_exists_by_schema",
            ],
            &["filter_previous_to_sources"],
        ),
    )?;
    let observer: Observer<'py> = Observer {
        adapter: arguments.value("adapter")?,
        connection: arguments.value("connection")?,
        observed_at: arguments.value("observed_at")?,
    };
    let run_id: Bound<'py, PyAny> = arguments.value("run_id")?;
    let sources: Vec<Bound<'py, PyAny>> = arguments
        .value("sources")?
        .try_iter()?
        .collect::<PyResult<_>>()?;
    let source_names: Option<Vec<String>> =
        if arguments.value("filter_previous_to_sources")?.is_truthy()? {
            let mut names: Vec<String> = sources
                .iter()
                .map(|source| source.getattr("name")?.extract())
                .collect::<PyResult<_>>()?;
            names.sort();
            Some(names)
        } else {
            None
        };
    let previous: Bound<'py, PyDict> = previous_records(
        &arguments,
        (&observer.adapter, &observer.connection),
        source_names.as_deref(),
    )?;
    let unknown_sources: Bound<'py, PyDict> = PyDict::new(py);
    let observed_sources: Bound<'py, PyDict> = PyDict::new(py);
    let mut adapter_sources: Vec<Bound<'py, PyAny>> = Vec::new();
    for source in &sources {
        if source.getattr("managed")?.is_truthy()? {
            continue;
        }
        let name: Bound<'py, PyAny> = source.getattr("name")?;
        let Some(observed) = observation_source(&observer.adapter, source)? else {
            unknown_sources.set_item(
                &name,
                unknown(&name, ("NO_FRESHNESS_CONFIG", text(py, NO_CONFIG_MESSAGE)))?,
            )?;
            continue;
        };
        observed_sources.set_item(&name, &observed)?;
        if freshness_strategy_is_adapter(&observed)? {
            adapter_sources.push(observed);
        }
    }
    let batch: Bound<'py, PyAny> = adapter_batch(&observer, &adapter_sources)?;
    unknown_sources.update(batch.getattr("unknown")?.downcast()?)?;
    let observations: Bound<'py, PyAny> = batch.getattr("observations")?;
    let mut observed_records: Vec<Bound<'py, PyAny>> = Vec::new();
    let changed: Bound<'py, PySet> = PySet::empty(py)?;
    let unchanged: Bound<'py, PySet> = PySet::empty(py)?;
    let age_statuses: Bound<'py, PyDict> = PyDict::new(py);
    for (name, source) in observed_sources.iter() {
        let observation: Bound<'py, PyAny> = if freshness_strategy_is_adapter(&source)? {
            let observation: Bound<'py, PyAny> = observations.call_method1("get", (&name,))?;
            if observation.is_none() {
                continue;
            }
            observation
        } else {
            match observe_configured(&observer, &source) {
                Ok(observation) => observation,
                Err(error) => {
                    let Some(message) = handled_message(py, &error)? else {
                        return Err(error);
                    };
                    let is_observation_error: bool = !error.value(py).is_instance(&imported(
                        py,
                        ADAPTER_EXCEPTIONS,
                        "AdapterUserError",
                    )?)?;
                    if is_observation_error && configuration_error(&message.extract::<String>()?) {
                        return Err(error);
                    }
                    unknown_sources.set_item(&name, unknown(&name, ("ERROR", message))?)?;
                    continue;
                }
            }
        };
        let record: Bound<'py, PyAny> = observation_record(&observation, &source, &run_id)?;
        observed_records.push(record.clone());
        let freshness: Bound<'py, PyAny> = source.getattr("freshness")?;
        let (policy, lag_tolerance) = if freshness.is_none() {
            (py.None().into_bound(py), None)
        } else {
            (
                freshness.getattr("age_policy")?,
                freshness
                    .getattr("lag_tolerance")?
                    .extract::<Option<String>>()?,
            )
        };
        let identity: Bound<'py, PyAny> = record.getattr("identity")?;
        if let Some(status) = age_policy(
            &policy,
            &observation.getattr("data_version")?,
            &observation.getattr("observed_at")?,
        )? {
            age_statuses.set_item(&identity, status)?;
        }
        match previous.get_item(&identity)? {
            None => changed.add(&identity)?,
            Some(previous_record) => {
                if equivalent(&previous_record, &record, lag_tolerance.as_deref())? {
                    unchanged.add(&identity)?;
                } else {
                    changed.add(&identity)?;
                }
            }
        }
    }
    let unknown_names: Bound<'py, PyDict> = sorted_dict(py, &unknown_sources)?;
    call_with(
        &imported(py, FRESHNESS_MODELS, "DirectSourceFreshnessPlanningResult")?,
        &[
            (
                "observed_records",
                PyTuple::new(py, sorted_by_identity(observed_records.into_iter())?)?.into_any(),
            ),
            (
                "previous_records",
                PyTuple::new(py, sorted_by_identity(previous.values().into_iter())?)?.into_any(),
            ),
            ("changed_identities", frozen(&changed)?),
            ("unchanged_identities", frozen(&unchanged)?),
            (
                "unknown_source_names",
                PyTuple::new(py, unknown_names.keys())?.into_any(),
            ),
            ("unknown_sources", unknown_names.into_any()),
            ("age_statuses", age_statuses.into_any()),
        ],
    )
}

/// `frozenset(items)`, keeping CPython's copied set layout and iteration order.
fn frozen<'py>(items: &Bound<'py, PySet>) -> PyResult<Bound<'py, PyAny>> {
    items.py().get_type::<PyFrozenSet>().call1((items,))
}

fn downstream_models<'py>(
    source_name: &Bound<'py, PyAny>,
    downstream_deps: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyFrozenSet>> {
    let py: Python<'py> = source_name.py();
    let key: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS, "CompiledObjectKey")?,
        &[
            (
                "resource_type",
                imported(py, COMPILE_TYPES, "CompiledResourceType")?.getattr("SOURCE")?,
            ),
            ("name", source_name.clone()),
        ],
    )?;
    build_downstream_model_name_closure(&PyTuple::new(py, [key])?.into_any(), downstream_deps)
}

/// Map changed and unknown source freshness roots to downstream model names.
#[pyfunction]
#[pyo3(signature = (*, source_freshness, scope))]
pub(crate) fn build_direct_source_freshness_propagation_result<'py>(
    source_freshness: &Bound<'py, PyAny>,
    scope: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = scope.py();
    let downstream_deps: Bound<'py, PyAny> = scope.getattr("downstream_deps")?;
    let changed: Bound<'py, PyDict> = PyDict::new(py);
    let unknown_sources: Bound<'py, PyDict> = PyDict::new(py);
    let errors: Bound<'py, PyDict> = PyDict::new(py);
    let stale: Bound<'py, PySet> = PySet::empty(py)?;
    let blocked: Bound<'py, PySet> = PySet::empty(py)?;
    for identity in source_freshness.getattr("changed_identities")?.try_iter()? {
        let identity: Bound<'py, PyAny> = identity?;
        let models: Bound<'py, PyFrozenSet> =
            downstream_models(&identity.getattr("source_name")?, &downstream_deps)?;
        stale.call_method1("update", (&models,))?;
        changed.set_item(identity, models)?;
    }
    for name in source_freshness
        .getattr("unknown_source_names")?
        .try_iter()?
    {
        let name: Bound<'py, PyAny> = name?;
        let models: Bound<'py, PyFrozenSet> = downstream_models(&name, &downstream_deps)?;
        stale.call_method1("update", (&models,))?;
        unknown_sources.set_item(name, models)?;
    }
    let error_status: Bound<'py, PyAny> =
        imported(py, FRESHNESS_TYPES, "SourceFreshnessAgeStatus")?.getattr("ERROR")?;
    for (identity, status) in source_freshness
        .getattr("age_statuses")?
        .downcast::<PyDict>()?
        .iter()
    {
        if status.ne(&error_status)? {
            continue;
        }
        let models: Bound<'py, PyFrozenSet> =
            downstream_models(&identity.getattr("source_name")?, &downstream_deps)?;
        blocked.call_method1("update", (&models,))?;
        errors.set_item(identity, models)?;
    }
    call_with(
        &imported(
            py,
            FRESHNESS_MODELS,
            "DirectSourceFreshnessPropagationResult",
        )?,
        &[
            ("changed_source_model_names", changed.into_any()),
            ("unknown_source_model_names", unknown_sources.into_any()),
            ("error_source_model_names", errors.into_any()),
            ("stale_model_names", frozen(&stale)?),
            ("blocked_model_names", frozen(&blocked)?),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(
        build_direct_source_freshness_planning_result,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        build_direct_source_freshness_propagation_result,
        module
    )?)?;
    Ok(())
}
