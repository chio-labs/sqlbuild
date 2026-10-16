//! Assemble model plan dataclasses from resolved plan decisions and authored model config.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyBool, PyDict, PyDictMethods, PyList, PyString, PyTuple};
use pyo3::{IntoPyObject, pyfunction};

use sqlbuild_analysis::planner_strategy::main::microbatch_lookback::microbatch_lookback;
use sqlbuild_analysis::planner_strategy::main::table_type_ddl::table_type_ddl;
use sqlbuild_analysis::planner_strategy::models::LookbackConfig;

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::call_with;
use crate::bindings::_helpers::cursor::scalars::sentinel_to_token;
use crate::bindings::_helpers::model_config::config_values::{
    config_bool, config_cursor_bound, config_int, config_str, config_string_tuple,
};
use crate::bindings::_helpers::native_host::adapter::AdapterHost;
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_strategy::constants::{
    CUSTOM_MATERIALIZATION, DDL_SEPARATOR, ENFORCED_CONTRACT, MICROBATCH_MODE,
};
use crate::bindings::_helpers::planner_strategy::cursor_inputs::model_values;
use crate::bindings::_helpers::planner_strategy::microbatch_limits::{replay_grain, unknown_grain};
use crate::bindings::_helpers::planner_strategy::microbatches::microbatch_limit_config;
use crate::bindings::_helpers::planner_strategy::values::{input_error, text};
use crate::bindings::_helpers::records::ids::{ErrorId, NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;

/// Model config keys copied to the plan entry as optional strings, with their entry fields.
const STRING_FIELDS: [(&str, &str); 15] = [
    ("incremental_strategy", "incremental_strategy"),
    ("incremental_mode", "incremental_mode"),
    ("microbatch_strategy", "microbatch_strategy"),
    ("cursor_watermark_mode", "cursor_watermark_mode"),
    ("cursor_type", "cursor_type"),
    ("cursor_grain", "cursor_grain"),
    ("batch_size", "batch_size"),
    (
        "unaccounted_partition_policy",
        "unaccounted_partition_policy",
    ),
    ("snapshot_strategy", "snapshot_strategy"),
    ("updated_at", "updated_at_column"),
    ("observed_at", "observed_at_column"),
    ("historical_input", "historical_input"),
    ("valid_from_column", "valid_from_column"),
    ("valid_to_column", "valid_to_column"),
    ("initial_valid_from", "initial_valid_from"),
];
/// Model config keys copied as optional strings that complete the snapshot settings.
const SNAPSHOT_POLICY_FIELDS: [&str; 2] = ["snapshot_full_refresh", "snapshot_schema_change"];
/// Plan decisions passed through to the entry unchanged.
const PASSED_FIELDS: [&str; 16] = [
    "action",
    "reason",
    "materialization_type",
    "resolved_sql",
    "cursor_column",
    "cursor_bounds",
    "empty_cursor_inputs",
    "waiting_on_empty_inputs",
    "cursor_input_relations",
    "microbatch_range",
    "start_cursor_override",
    "end_cursor_override",
    "future_cursor_config",
    "start_cursor_config",
    "invocation_time",
    "backfill",
];
/// Change-detection facts copied to the entry.
const CHANGE_FIELDS: [&str; 8] = [
    "fingerprint_metadata_json",
    "previous_metadata_json",
    "fingerprint_version_hash",
    "previous_version_hash",
    "query_changed",
    "config_changed",
    "schema_findings",
    "changed_functions",
];

fn none(py: Python<'_>) -> Bound<'_, PyAny> {
    py.None().into_bound(py)
}

fn or_none<'py>(py: Python<'py>, value: Option<Bound<'py, PyAny>>) -> Bound<'py, PyAny> {
    value.unwrap_or_else(|| none(py))
}

/// `ColumnInfo(name=..., type=...)`.
fn column_info<'py>(
    class: &Bound<'py, PyAny>,
    (name, column_type): (Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    call_with(class, &[("name", name), ("type", column_type)])
}

/// Declared schema columns as `ColumnInfo`: typed columns only, or every column with an empty default type.
fn schema_columns<'py>(
    model: &Bound<'py, PyAny>,
    typed_only: bool,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = model.py();
    let entry: Bound<'py, PyAny> = model.getattr("schema_entry")?;
    if entry.is_none() {
        return Ok(PyTuple::empty(py));
    }
    let class: Bound<'py, PyAny> = host::entry(py, AdapterHost::ColumnInfo)?;
    let mut columns: Vec<Bound<'py, PyAny>> = Vec::new();
    for column in entry.getattr("columns")?.try_iter()? {
        let column: Bound<'py, PyAny> = column?;
        let column_type: Bound<'py, PyAny> = column.getattr("type")?;
        if typed_only && column_type.is_none() {
            continue;
        }
        let column_type: Bound<'py, PyAny> = if typed_only || column_type.is_truthy()? {
            column_type
        } else {
            PyString::new(py, "").into_any()
        };
        columns.push(column_info(&class, (column.getattr("name")?, column_type))?);
    }
    PyTuple::new(py, columns)
}

/// A string or list-of-strings config value as a tuple of strings.
fn string_list<'py>(values: &Bound<'py, PyAny>, key: &str) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = values.py();
    let raw: Bound<'py, PyAny> = values.call_method1("get", (key,))?;
    if raw.is_instance_of::<PyString>() {
        return PyTuple::new(py, [raw]);
    }
    if raw.is_instance_of::<PyList>() {
        let items: Vec<Bound<'py, PyAny>> = raw
            .try_iter()?
            .filter(|item| {
                item.as_ref()
                    .map_or(true, |item| item.is_instance_of::<PyString>())
            })
            .collect::<PyResult<_>>()?;
        return PyTuple::new(py, items);
    }
    Ok(PyTuple::empty(py))
}

/// The model's `on_schema_change` policy, rejecting unknown values.
fn on_schema_change<'py>(model: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = model.py();
    let raw: Bound<'py, PyAny> = model_values(model)?.call_method1("get", ("on_schema_change",))?;
    if raw.is_none() {
        return Ok(raw);
    }
    if raw.is_instance_of::<PyString>() {
        match registry::class(py, RecordId::OnSchemaChange)?.call1((&raw,)) {
            Ok(policy) => return Ok(policy),
            Err(error) if !error.is_instance_of::<PyValueError>(py) => return Err(error),
            Err(_) => {}
        }
    }
    Err(input_error(
        py,
        ErrorId::PlannerInput,
        &format!(
            "model '{}': unknown on_schema_change '{}'",
            model_reads::model_name(model)?,
            raw.str()?
        ),
        None,
    ))
}

/// Whether the model's schema enforces declared column types.
fn type_enforcement<'py>(model: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = model.py();
    let entry: Bound<'py, PyAny> = model.getattr("schema_entry")?;
    if !entry.is_none() {
        let enforcement: Bound<'py, PyAny> = entry.getattr("type_enforcement")?;
        if !enforcement.is_none() {
            return Ok(enforcement);
        }
    }
    Ok(PyBool::new(py, false).to_owned().into_any())
}

/// The explicit or default lookback of a microbatch model at the effective grain.
fn lookback_of(
    model: &Bound<'_, PyAny>,
    effective_grain: Option<String>,
) -> PyResult<Option<String>> {
    let values: Bound<'_, PyAny> = model_values(model)?;
    let read = |key: &str| -> PyResult<Option<String>> {
        config_str(&values, key)?
            .map(|value| text(&value))
            .transpose()
    };
    let config = LookbackConfig {
        lookback: read("lookback")?,
        incremental_strategy: read("incremental_strategy")?,
        batch_size: read("batch_size")?,
        grain: match effective_grain.filter(|grain| !grain.is_empty()) {
            Some(grain) => Some(grain),
            None => read("cursor_grain")?,
        },
    };
    microbatch_lookback(&config).map_err(|error| unknown_grain(model.py(), error))
}

/// Resolve explicit or default lookback for one microbatch model.
#[pyfunction]
#[pyo3(signature = (*, model, effective_grain = None))]
pub(crate) fn resolve_microbatch_lookback(
    model: &Bound<'_, PyAny>,
    effective_grain: Option<String>,
) -> PyResult<Option<String>> {
    lookback_of(model, effective_grain)
}

/// Declared seed columns with types, as `ColumnInfo`.
#[pyfunction]
#[pyo3(signature = (seed))]
pub(crate) fn extract_seed_columns<'py>(seed: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    schema_columns(seed, true)
}

/// The adapter-rendered logical DDL of one plan action.
fn logical_ddl<'py>(
    request: &Request<'_, 'py>,
    (unique_key, merge_exclude): (&Bound<'py, PyTuple>, &Bound<'py, PyTuple>),
    (warehouse_columns, cursor_bounds): (&Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> PyResult<String> {
    let py: Python<'py> = request.py();
    let adapter: Bound<'py, PyAny> = request.get("adapter")?;
    let model: Bound<'py, PyAny> = request.get("model")?;
    let destination: Bound<'py, PyAny> = model_reads::destination(&model)?;
    let qualified: Bound<'py, PyAny> = destination.getattr("qualified_name")?;
    let qualified: Bound<'py, PyAny> = if qualified.is_truthy()? {
        qualified
    } else {
        destination.getattr("name")?
    };
    let sql: Bound<'py, PyAny> = request.get("resolved_sql")?;
    let mut pairs: Vec<(&str, Bound<'py, PyAny>)> = vec![("destination", qualified), ("sql", sql)];
    let cursor_column: Bound<'py, PyAny> = request.get("cursor_column")?;
    let method: &str = match text(&request.get("action")?)?.as_str() {
        "create_view" => "render_create_view_as",
        "create_table" => "render_create_table_as",
        "incremental_append" => "render_append",
        "incremental_delete_insert" if !cursor_column.is_none() && !cursor_bounds.is_none() => {
            let values: Bound<'py, PyAny> = model_values(&model)?;
            let start = sentinel_to_token(&cursor_bounds.getattr("start")?)?;
            let end = sentinel_to_token(&cursor_bounds.getattr("end")?)?;
            pairs.push(("cursor_column", cursor_column));
            pairs.push(("cursor_start", PyString::new(py, &start).into_any()));
            pairs.push(("cursor_end", PyString::new(py, &end).into_any()));
            pairs.push((
                "cursor_type",
                or_none(py, config_str(&values, "cursor_type")?),
            ));
            "render_delete_insert_cursor"
        }
        "incremental_delete_insert" => {
            pairs.push(("unique_key", unique_key.clone().into_any()));
            "render_delete_insert"
        }
        "incremental_merge" => {
            let mut source_columns: Vec<Bound<'py, PyAny>> = Vec::new();
            for column in warehouse_columns.try_iter()? {
                source_columns.push(column?.getattr("name")?);
            }
            pairs.push(("unique_key", unique_key.clone().into_any()));
            pairs.push((
                "source_columns",
                PyTuple::new(py, source_columns)?.into_any(),
            ));
            pairs.push(("exclude_columns", merge_exclude.clone().into_any()));
            "render_merge"
        }
        _ => return Ok(String::new()),
    };
    let statements: Vec<String> = call_with(&adapter.getattr(method)?, &pairs)?
        .try_iter()?
        .map(|statement| statement?.extract())
        .collect::<PyResult<_>>()?;
    Ok(statements.join(DDL_SEPARATOR))
}

/// The custom materialization name, config and placeholders of a custom model.
fn custom_fields<'py>(
    values: &Bound<'py, PyAny>,
    custom: bool,
    entry: &Bound<'py, PyDict>,
) -> PyResult<()> {
    let py: Python<'py> = values.py();
    let config: Bound<'py, PyDict> = PyDict::new(py);
    let placeholders: Bound<'py, PyDict> = PyDict::new(py);
    let mut name: Bound<'py, PyAny> = none(py);
    if custom {
        let raw_name: Bound<'py, PyAny> = values.call_method1("get", ("materialized",))?;
        if raw_name.is_instance_of::<PyString>() {
            name = raw_name;
        }
        if let Ok(raw) = values
            .call_method1("get", ("config",))?
            .downcast::<PyDict>()
        {
            for (key, value) in raw.iter() {
                config.set_item(key.str()?, value)?;
            }
        }
        if let Ok(raw) = values
            .call_method1("get", ("placeholders",))?
            .downcast::<PyDict>()
        {
            for (key, value) in raw.iter() {
                placeholders.set_item(key.str()?, value.str()?)?;
            }
        }
    }
    entry.set_item("custom_materialization_name", name)?;
    entry.set_item("custom_config", config)?;
    entry.set_item("custom_placeholders", placeholders)
}

/// The model's base warnings followed by its cursor type warning.
fn model_warnings<'py>(
    request: &Request<'_, 'py>,
    (schema_actions, policy): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    (enforcement, warehouse_columns): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = request.py();
    let model: Bound<'py, PyAny> = request.get("model")?;
    let name: Bound<'py, PyAny> = model_reads::name_object(&model)?;
    let mut warnings: Vec<Bound<'py, PyAny>> = call_with(
        &registry::native(py, NativeAttr::BuildModelWarnings)?,
        &[
            ("model_name", name.clone()),
            ("materialization_type", request.get("materialization_type")?),
            ("change_result", request.get("change_result")?),
            ("schema_actions", schema_actions.clone()),
            ("on_schema_change", policy.clone()),
            ("type_enforcement", enforcement.clone()),
        ],
    )?
    .try_iter()?
    .collect::<PyResult<_>>()?;
    let cursor_warning: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::CheckCursorTypeConsistency)?,
        &[
            ("model_name", name),
            ("cursor_column", request.get("cursor_column")?),
            (
                "cursor_type",
                or_none(py, config_str(&model_values(&model)?, "cursor_type")?),
            ),
            ("warehouse_columns", warehouse_columns.clone()),
            ("sql_analysis_enabled", request.get("sql_analysis_enabled")?),
        ],
    )?;
    if !cursor_warning.is_none() {
        warnings.push(cursor_warning);
    }
    PyTuple::new(py, warnings)
}

/// The cursor bounds the logical DDL renders: placeholders for runtime-owned windows, else the batch range or cursor bounds.
fn ddl_cursor_bounds<'py>(request: &Request<'_, 'py>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let microbatch_range: Bound<'py, PyAny> = request.get("microbatch_range")?;
    Ok(
        if request.get("runtime_owned_cursor_bounds")?.is_truthy()?
            && !request.get("cursor_column")?.is_none()
        {
            let sentinel: Bound<'py, PyAny> = host::entry(py, ExecutorHost::BoundSentinel)?;
            call_with(
                &registry::class(py, RecordId::CursorBounds)?,
                &[
                    ("start", sentinel.getattr("START")?),
                    ("end", sentinel.getattr("END")?),
                ],
            )?
        } else if microbatch_range.is_truthy()? {
            microbatch_range.clone()
        } else {
            request.get("cursor_bounds")?
        },
    )
}

/// Copy the model's authored strategy, cursor, batch and snapshot settings onto the entry.
fn config_fields<'py>(
    request: &Request<'_, 'py>,
    values: &Bound<'py, PyAny>,
    entry: &Bound<'py, PyDict>,
) -> PyResult<()> {
    let py: Python<'py> = request.py();
    let model: Bound<'py, PyAny> = request.get("model")?;
    for (key, field) in STRING_FIELDS {
        entry.set_item(field, or_none(py, config_str(values, key)?))?;
    }
    for key in SNAPSHOT_POLICY_FIELDS {
        entry.set_item(key, or_none(py, config_str(values, key)?))?;
    }
    for key in ["cursor_start", "cursor_end"] {
        entry.set_item(key, or_none(py, config_cursor_bound(values, key)?))?;
    }
    let microbatch: bool = match config_str(values, "incremental_mode")? {
        Some(mode) => mode.eq(MICROBATCH_MODE)?,
        None => false,
    };
    let lookback: Option<String> = if microbatch {
        let read = |key: &str| -> PyResult<Option<String>> {
            config_str(values, key)?
                .map(|value| text(&value))
                .transpose()
        };
        let grain: Option<String> = replay_grain(
            (
                read("cursor_type")?,
                read("microbatch_strategy")?,
                read("cursor_grain")?,
            ),
            &request.get("cursor_input_relations")?,
        )?;
        lookback_of(&model, grain)?
    } else {
        config_str(values, "lookback")?
            .map(|value| text(&value))
            .transpose()?
    };
    entry.set_item("lookback", lookback)?;
    let concurrency: Bound<'py, PyAny> = match config_int(values, "batch_concurrency")? {
        Some(concurrency) if concurrency.is_truthy()? => concurrency,
        _ => 1_i64.into_pyobject(py)?.into_any(),
    };
    entry.set_item("batch_concurrency", concurrency)?;
    let (limit, limit_action) = microbatch_limit_config(values)?;
    entry.set_item("microbatch_limit", or_none(py, limit))?;
    entry.set_item(
        "declared_microbatch_limit_action",
        or_none(py, limit_action),
    )?;
    entry.set_item("check_columns", string_list(values, "check_columns")?)?;
    let hard_deletes: Bound<'py, PyAny> = match config_bool(values, "invalidate_hard_deletes")? {
        Some(flag) if flag.is_truthy()? => flag,
        _ => PyBool::new(py, false).to_owned().into_any(),
    };
    entry.set_item("invalidate_hard_deletes", hard_deletes)?;
    Ok(())
}

/// Copy the model's declared columns and contract onto the entry.
fn contract_fields<'py>(
    model: &Bound<'py, PyAny>,
    values: &Bound<'py, PyAny>,
    entry: &Bound<'py, PyDict>,
) -> PyResult<()> {
    let py: Python<'py> = model.py();
    entry.set_item("declared_columns", schema_columns(model, true)?)?;
    entry.set_item(
        "contract_enforced",
        values
            .call_method1("get", ("contract",))?
            .eq(ENFORCED_CONTRACT)?,
    )?;
    entry.set_item("contract_columns", schema_columns(model, false)?)?;
    let schema_entry: Bound<'py, PyAny> = model.getattr("schema_entry")?;
    entry.set_item(
        "contract_dynamic_columns",
        if schema_entry.is_none() {
            PyTuple::empty(py).into_any()
        } else {
            schema_entry.getattr("dynamic_columns")?
        },
    )?;
    Ok(())
}

/// Build a model plan entry and its warnings from resolved plan decisions, keeping the Python dataclasses.
#[pyfunction]
#[pyo3(signature = (**request))]
pub(crate) fn assemble_model_plan_entry<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let request = Request::new("assemble_model_plan_entry", request)?;
    let py: Python<'py> = request.py();
    let model: Bound<'py, PyAny> = request.get("model")?;
    let values: Bound<'py, PyAny> = model_values(&model)?;
    let change: Bound<'py, PyAny> = request.get("change_result")?;
    let snapshot: Bound<'py, PyAny> = request.get("snapshot")?;
    let name: Bound<'py, PyAny> = model_reads::name_object(&model)?;
    let policy: Bound<'py, PyAny> = on_schema_change(&model)?;
    let schema_actions: Bound<'py, PyAny> = call_with(
        &registry::native(py, NativeAttr::ResolveSchemaActions)?,
        &[
            ("schema_findings", change.getattr("schema_findings")?),
            ("on_schema_change", policy.clone()),
        ],
    )?;
    let enforcement: Bound<'py, PyAny> = type_enforcement(&model)?;
    let warehouse_columns: Bound<'py, PyAny> = snapshot
        .getattr("existing_columns")?
        .call_method1("get", (&name, PyTuple::empty(py)))?;
    let warnings: Bound<'py, PyTuple> = model_warnings(
        &request,
        (&schema_actions, &policy),
        (&enforcement, &warehouse_columns),
    )?;
    let unique_key: Bound<'py, PyTuple> = string_list(&values, "unique_key")?;
    let merge_exclude: Bound<'py, PyTuple> = config_string_tuple(&values, "merge_exclude_columns")?
        .unwrap_or_else(|| PyTuple::empty(py));
    let table_type: Bound<'py, PyAny> = model
        .getattr("config")?
        .getattr("table_type")?
        .getattr("value")?
        .getattr("value")?;
    let ddl: String = logical_ddl(
        &request,
        (&unique_key, &merge_exclude),
        (&warehouse_columns, ddl_cursor_bounds(&request)?),
    )?;
    let entry: Bound<'py, PyDict> = PyDict::new(py);
    entry.set_item("key", model_reads::model_key(&model)?)?;
    entry.set_item("name", &name)?;
    entry.set_item("relative_path", model.getattr("relative_path")?)?;
    entry.set_item("destination", model_reads::destination(&model)?)?;
    entry.set_item("fingerprint_query_sql", model_reads::query_sql(&model)?)?;
    entry.set_item("logical_ddl", table_type_ddl(&ddl, &text(&table_type)?))?;
    for field in PASSED_FIELDS {
        entry.set_item(field, request.get(field)?)?;
    }
    for field in CHANGE_FIELDS {
        entry.set_item(field, change.getattr(field)?)?;
    }
    config_fields(&request, &values, &entry)?;
    entry.set_item("unique_key", unique_key)?;
    entry.set_item("merge_exclude_columns", merge_exclude)?;
    entry.set_item("table_type", table_type)?;
    entry.set_item("on_schema_change", policy)?;
    entry.set_item("type_enforcement", enforcement)?;
    contract_fields(&model, &values, &entry)?;
    for field in ["pre_hooks", "post_hooks"] {
        entry.set_item(field, request.get(field)?)?;
    }
    let fingerprint: Bound<'py, PyAny> = snapshot
        .getattr("fingerprints")?
        .getattr("models")?
        .call_method1("get", (&name,))?;
    entry.set_item(
        "previous_query_sql",
        if fingerprint.is_none() {
            fingerprint
        } else {
            fingerprint.getattr("definition")?
        },
    )?;
    entry.set_item("schema_actions", schema_actions)?;
    custom_fields(
        &values,
        text(&request.get("materialization_type")?)? == CUSTOM_MATERIALIZATION,
        &entry,
    )?;
    let plan_entry: Bound<'py, PyAny> =
        registry::class(py, RecordId::ModelPlanEntry)?.call((), Some(&entry))?;
    PyTuple::new(py, [plan_entry, warnings.into_any()])
}
