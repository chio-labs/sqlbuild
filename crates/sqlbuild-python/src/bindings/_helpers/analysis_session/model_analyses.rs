//! One compile's native model analysis session, with Python's catalog and metric bookkeeping.

use std::path::PathBuf;

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{IntoPyDict, PyDict, PyDictMethods, PyFrozenSet, PyList, PyString, PyTuple};
use sqlbuild_analysis::assembly::analysis_session::types::Shapes;

use crate::bindings::_helpers::analysis_session::profile_inputs::{
    case_sensitive_shapes, nullability_rules, profile_dialect, return_types, shape_rows,
};
use crate::bindings::_helpers::analysis_session::session::{
    CacheStatsRow, NativeModelAnalysisSession, RequestRow, start_model_analysis_session,
};
use crate::bindings::_helpers::analysis_session::stage_functions::family_rows;
use crate::bindings::_helpers::attachments::cursor_intrinsics::analysis_cursor_sql;
use crate::bindings::_helpers::cache::native_store::{content_digest, current_code_identity};
use crate::bindings::_helpers::compile_driver::analysis_cache::record_analysis_cache_metrics;
use crate::bindings::_helpers::compiled_project::model_input_view::{
    AttachedSchema, attached_schema, input_model_name,
};
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::construct::enum_member;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_get;
use crate::bindings::_helpers::records::fields::mapping_items;
use crate::bindings::_helpers::records::ids::RecordId;
use crate::bindings::_helpers::semantic_shapes::shapes::{VALID_FROM_DEFAULT, VALID_TO_DEFAULT};

const LOGGING_MODULE: &str = "logging";
const DEBUG_LOGGER: &str = "sqlbuild.compile";
const ANALYSIS_FAILURE_MESSAGE: &str = "native compact query analysis failed";
const STORE_FAILURE_MESSAGE: &str = "native model analysis cache not read or saved";
const STORE_FILE_NAME: &str = "model-analyses.bin";
const STORE_VERSION: &str = "native-model-analysis-store-v1";

/// What one compile's model analysis reads: the analysed models and the relation facts.
pub(crate) struct ModelAnalysisRequest<'py> {
    pub(crate) model_inputs: Vec<Bound<'py, PyAny>>,
    pub(crate) profile: Bound<'py, PyAny>,
    pub(crate) column_types: Bound<'py, PyAny>,
    pub(crate) nullability: Bound<'py, PyAny>,
    pub(crate) complete_schemas: Bound<'py, PyAny>,
    pub(crate) dynamic_families: Bound<'py, PyAny>,
    pub(crate) rich_type_inference: bool,
    /// The `AnalysisCacheContext`, or `None` when the analysis store is bypassed.
    pub(crate) cache: Bound<'py, PyAny>,
}

/// Each analysed model's position in the finished session, those that succeeded, and the session.
pub(crate) struct ModelAnalyses<'py> {
    pub(crate) positions: Bound<'py, PyDict>,
    pub(crate) succeeded: Bound<'py, PyFrozenSet>,
    /// The finished session, or `None` when no model was analysed.
    pub(crate) session: Option<Bound<'py, NativeModelAnalysisSession>>,
}

/// Each model's analysis by name and the finished session; a native internal failure raises.
pub(crate) fn analyze_models<'py>(
    request: &ModelAnalysisRequest<'py>,
) -> PyResult<ModelAnalyses<'py>> {
    let py: Python<'py> = request.profile.py();
    if request.model_inputs.is_empty() {
        return Ok(ModelAnalyses {
            positions: PyDict::new(py),
            succeeded: PyFrozenSet::empty(py)?,
            session: None,
        });
    }
    let catalog: Bound<'py, PyAny> = native_field(&request.profile, "binding_catalog")?;
    let (rules, adapter_rules) = nullability_rules(&request.profile)?;
    let session_request: RequestRow = session_request(request, &catalog, rules)?.extract()?;
    let (cache, adapter) = match adapter_rules {
        Some((adapter, nullability)) => (None, Some((adapter, nullability))),
        None => (analysis_store(request)?, None),
    };
    let session: Bound<'py, NativeModelAnalysisSession> = Bound::new(
        py,
        start_model_analysis_session(
            native_field(&catalog, "native")?.extract()?,
            session_request,
            cache,
            adapter,
        )?,
    )?;
    run_session(request, &catalog, &session)
}

/// The session request row, in the order the native session reads it.
fn session_request<'py>(
    request: &ModelAnalysisRequest<'py>,
    catalog: &Bound<'py, PyAny>,
    rules: Vec<(String, String)>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = catalog.py();
    let profile: &Bound<'py, PyAny> = &request.profile;
    let mut families: Vec<(String, Vec<_>)> = Vec::new();
    for item in mapping_items(&request.dynamic_families)?.try_iter()? {
        let (name, declared): (String, Bound<'py, PyAny>) = item?.extract()?;
        families.push((name, family_rows(&declared)?));
    }
    let items: Vec<Bound<'py, PyAny>> = vec![
        profile_dialect(profile)?.into_bound_py_any(py)?,
        case_sensitive_shapes(profile, &native_field(profile, "sql_analysis_dialect")?)?
            .into_bound_py_any(py)?,
        return_types(profile)?.into_bound_py_any(py)?,
        rules.into_bound_py_any(py)?,
        request.rich_type_inference.into_bound_py_any(py)?,
        shape_rows(&request.column_types)?.into_bound_py_any(py)?,
        shape_rows(&request.nullability)?.into_bound_py_any(py)?,
        shape_rows(&request.complete_schemas)?.into_bound_py_any(py)?,
        shape_rows(&native_field(catalog, "schemas")?)?.into_bound_py_any(py)?,
        families.into_bound_py_any(py)?,
        model_rows(py, &request.model_inputs)?,
    ];
    Ok(PyTuple::new(py, items)?.into_any())
}

/// The analysis store's path and environment, or None where Python bypasses its cache.
fn analysis_store(request: &ModelAnalysisRequest<'_>) -> PyResult<Option<(PathBuf, String)>> {
    let context: &Bound<'_, PyAny> = &request.cache;
    if context.is_none() {
        return Ok(None);
    }
    let path: PathBuf = native_field(context, "root")?
        .div(STORE_FILE_NAME)?
        .extract()?;
    let environment: String = content_digest(vec![
        STORE_VERSION.to_owned(),
        current_code_identity(context.py())?,
        native_field(context, "shared_fingerprint")?.extract()?,
        native_field(context, "signature_namespace")?.extract()?,
    ]);
    Ok(Some((path, environment)))
}

/// Run and finish the session, leaving Python's catalog and metrics as its analysis did.
fn run_session<'py>(
    request: &ModelAnalysisRequest<'py>,
    catalog: &Bound<'py, PyAny>,
    session: &Bound<'py, NativeModelAnalysisSession>,
) -> PyResult<ModelAnalyses<'py>> {
    let py: Python<'py> = catalog.py();
    let python: &[Bound<'py, PyAny>] = &request.model_inputs;
    let types: Bound<'py, PyDict> = copied(&request.column_types)?;
    let nullability: Bound<'py, PyDict> = copied(&request.nullability)?;
    let (publications, failures) = session.borrow_mut().run(py)?;
    for failure in failures {
        log_debug(
            py,
            ANALYSIS_FAILURE_MESSAGE,
            PyString::new(py, &failure).as_any(),
        )?;
    }
    let unknown: Bound<'py, PyAny> = enum_member(py, RecordId::InferredNullability, "UNKNOWN")?;
    for (name, shape) in publications {
        let published: Bound<'py, PyDict> = shape.into_py_dict(py)?;
        types.call_method1("setdefault", (&name, &published))?;
        let defaults: Bound<'py, PyDict> = PyDict::new(py);
        for column in published.keys() {
            defaults.set_item(column, &unknown)?;
        }
        nullability.call_method1("setdefault", (&name, defaults))?;
    }
    let (additions, analysis_names, succeeded) = session.borrow_mut().finish(py)?;
    record_catalog_changes(catalog, additions, &analysis_names, (&types, &nullability))?;
    record_cache(py, python, session.borrow().cache_stats())?;
    let positions: Bound<'py, PyDict> = PyDict::new(py);
    let mut succeeded_names: Vec<Bound<'py, PyAny>> = Vec::new();
    for (index, (model_input, success)) in python.iter().zip(&succeeded).enumerate() {
        let name: Bound<'py, PyAny> = PyString::new(py, &input_model_name(model_input)?).into_any();
        positions.set_item(&name, index)?;
        if *success {
            succeeded_names.push(name);
        }
    }
    Ok(ModelAnalyses {
        positions,
        succeeded: PyFrozenSet::new(py, succeeded_names)?,
        session: Some(session.clone()),
    })
}

/// Leave Python's binding catalog as its own analysis would have.
fn record_catalog_changes<'py>(
    catalog: &Bound<'py, PyAny>,
    schema_additions: Shapes,
    analysis_names: &[String],
    (types, nullability): (&Bound<'py, PyDict>, &Bound<'py, PyDict>),
) -> PyResult<()> {
    let py: Python<'py> = catalog.py();
    let schemas: Bound<'py, PyAny> = native_field(catalog, "schemas")?;
    let additions: Bound<'py, PyDict> = PyDict::new(py);
    for (name, shape) in schema_additions {
        if !schemas.contains(&name)? {
            additions.set_item(name, shape.into_py_dict(py)?)?;
        }
    }
    schemas.call_method1("update", (&additions,))?;
    if !additions.is_empty() {
        native_field(catalog, "native")?.call_method1("update_relations", (&additions,))?;
    }
    let selected_types: Bound<'py, PyDict> = PyDict::new(py);
    let selected_nullability: Bound<'py, PyDict> = PyDict::new(py);
    for name in analysis_names {
        if let Some(shape) = types.get_item(name)? {
            selected_types.set_item(name, shape)?;
        }
    }
    for name in analysis_names {
        if let Some(shape) = nullability.get_item(name)? {
            selected_nullability.set_item(name, shape)?;
        }
    }
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("types", selected_types)?;
    arguments.set_item("nullability", selected_nullability)?;
    native_field(catalog, "prepare_analysis")?.call((), Some(&arguments))?;
    Ok(())
}

fn record_cache(
    py: Python<'_>,
    python: &[Bound<'_, PyAny>],
    stats: Option<CacheStatsRow>,
) -> PyResult<()> {
    let Some((hits, misses, _, failure)) = stats else {
        return record_metrics((0, 0, python.len()));
    };
    if let Some(failure) = failure {
        log_debug(
            py,
            STORE_FAILURE_MESSAGE,
            PyString::new(py, &failure).as_any(),
        )?;
    }
    if hits + misses == 0 {
        return record_metrics((0, 0, python.len()));
    }
    record_metrics((hits, misses, 0))
}

/// Record the analysis cache entries a native session read, missed and bypassed.
fn record_metrics((hits, misses, bypasses): (usize, usize, usize)) -> PyResult<()> {
    record_analysis_cache_metrics((0, hits, misses, bypasses));
    Ok(())
}

/// Each model's native request row, in analysis order.
fn model_rows<'py>(
    py: Python<'py>,
    model_inputs: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let enforced: Bound<'py, PyAny> = enum_member(py, RecordId::ContractPolicy, "ENFORCED")?;
    let snapshot: Bound<'py, PyAny> = enum_member(py, RecordId::MaterializationType, "SNAPSHOT")?;
    let mut rows: Vec<Bound<'py, PyAny>> = Vec::with_capacity(model_inputs.len());
    for model_input in model_inputs {
        let values: Bound<'py, PyAny> = native_field(model_input, "config")?.getattr("values")?;
        let get = |key: &str| mapping_get(&values, key);
        let query_sql: Bound<'py, PyAny> = PyString::new(
            py,
            &analysis_cursor_sql(
                py,
                &native_field(model_input, "query_sql")?.extract::<String>()?,
                &get("cursor_type")?,
            )?,
        )
        .into_any();
        let mut placeholders: Vec<(String, String)> = Vec::new();
        let raw: Bound<'py, PyAny> = get("placeholders")?;
        if raw.is_instance_of::<PyDict>() {
            for item in mapping_items(&raw)?.try_iter()? {
                let (key, value): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
                placeholders.push((key.str()?.extract()?, value.str()?.extract()?));
            }
        }
        let mut references: Vec<(String, String)> = Vec::new();
        for row in native_field(model_input, "reference_rows")?.try_iter()? {
            let row: Bound<'py, PyAny> = row?;
            references.push((
                row.get_item(0)?.str()?.extract()?,
                row.get_item(1)?.extract()?,
            ));
        }
        let schema: Option<AttachedSchema<'py>> = attached_schema(model_input)?;
        let recovers: bool = get("contract")?.eq(&enforced)?
            || schema
                .as_ref()
                .is_some_and(|schema| schema.type_enforcement);
        let snapshot_columns: Option<(String, String)> = if get("materialized")?.eq(&snapshot)? {
            Some((
                or_default(&get("valid_from_column")?, VALID_FROM_DEFAULT)?,
                or_default(&get("valid_to_column")?, VALID_TO_DEFAULT)?,
            ))
        } else {
            None
        };
        let families = match &schema {
            Some(schema) => family_rows(&schema.dynamic_columns)?,
            None => Vec::new(),
        };
        let row: Vec<Bound<'py, PyAny>> = vec![
            input_model_name(model_input)?.into_bound_py_any(py)?,
            query_sql,
            placeholders.into_bound_py_any(py)?,
            references.into_bound_py_any(py)?,
            recovers.into_bound_py_any(py)?,
            snapshot_columns.into_bound_py_any(py)?,
            families.into_bound_py_any(py)?,
        ];
        rows.push(PyTuple::new(py, row)?.into_any());
    }
    Ok(PyList::new(py, rows)?.into_any())
}

/// `str(value or default)`.
fn or_default(value: &Bound<'_, PyAny>, default: &str) -> PyResult<String> {
    if value.is_truthy()? {
        return value.str()?.extract();
    }
    Ok(default.to_owned())
}

fn log_debug(py: Python<'_>, message: &str, failure: &Bound<'_, PyAny>) -> PyResult<()> {
    let arguments: Bound<'_, PyDict> = PyDict::new(py);
    arguments.set_item(
        "logger",
        py.import(LOGGING_MODULE)?
            .getattr("getLogger")?
            .call1((DEBUG_LOGGER,))?,
    )?;
    arguments.set_item("message", message)?;
    arguments.set_item("sqlbuild_error", failure)?;
    host::entry(py, ExecutorHost::LogDebugEvent)?.call((), Some(&arguments))?;
    Ok(())
}

/// `dict(mapping)`.
fn copied<'py>(mapping: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyDict>> {
    let copy: Bound<'py, PyDict> = PyDict::new(mapping.py());
    copy.update(mapping.downcast()?)?;
    Ok(copy)
}
