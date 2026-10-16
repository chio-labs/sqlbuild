//! One compile's native model analysis session, with Python's catalog and metric bookkeeping.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyList, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::analysis_session::profile_inputs::{
    case_sensitive_shapes, nullability_rules, profile_dialect, return_types, shape_rows,
};
use crate::bindings::_helpers::analysis_session::stage_functions::family_rows;
use crate::bindings::_helpers::attachments::cursor_intrinsics::analysis_cursor_sql;
use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::cache::native_store::current_code_identity;
use crate::bindings::_helpers::compile_driver::analysis_cache::record_analysis_cache_metrics;
use crate::bindings::_helpers::compiled_project::model_input_view::{
    AttachedSchema, attached_schema,
};
use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::semantic_shapes::shapes::{VALID_FROM_DEFAULT, VALID_TO_DEFAULT};

const LOGGING_MODULE: &str = "logging";
const DEBUG_LOGGER: &str = "sqlbuild.compile";
const ANALYSIS_FAILURE_MESSAGE: &str = "native compact query analysis failed";
const STORE_FAILURE_MESSAGE: &str = "native model analysis cache not read or saved";
const STORE_FILE_NAME: &str = "model-analyses.bin";
const STORE_VERSION: &str = "native-model-analysis-store-v1";

/// Each model's analysis by name and the finished session; a native internal failure raises.
#[pyfunction]
#[pyo3(signature = (**request))]
fn analyze_native_model_sql<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let request = Request::new("analyze_native_model_sql", request)?;
    let py: Python<'py> = request.py();
    let request: Bound<'py, PyAny> = request.get("request")?;
    let analyses_class: Bound<'py, PyAny> = registry::class(py, RecordId::NativeModelAnalyses)?;
    let model_inputs: Bound<'py, PyAny> = request.getattr("model_inputs")?;
    if !model_inputs.is_truthy()? {
        let arguments: Bound<'py, PyDict> = PyDict::new(py);
        arguments.set_item("positions", PyDict::new(py))?;
        arguments.set_item("succeeded", PyFrozenSet::empty(py)?)?;
        arguments.set_item("session", py.None())?;
        return analyses_class.call((), Some(&arguments));
    }
    let profile: Bound<'py, PyAny> = request.getattr("inference_profile")?;
    let catalog: Bound<'py, PyAny> = profile.getattr("binding_catalog")?;
    let python: Vec<Bound<'py, PyAny>> = model_inputs.try_iter()?.collect::<PyResult<_>>()?;
    let (rules, adapter_rules) = nullability_rules(&profile)?;
    let session_request: Bound<'py, PyAny> = session_request(&request, &python, &catalog, rules)?;
    let (cache, adapter): (Bound<'py, PyAny>, Bound<'py, PyAny>) = match adapter_rules {
        Some((adapter, nullability)) => (
            py.None().into_bound(py),
            PyTuple::new(
                py,
                [
                    adapter.into_any().into_bound(py),
                    nullability.into_bound(py),
                ],
            )?
            .into_any(),
        ),
        None => (analysis_store(&request)?, py.None().into_bound(py)),
    };
    let session: Bound<'py, PyAny> = registry::native(py, NativeAttr::StartModelAnalysisSession)?
        .call1((
        catalog.getattr("native")?,
        session_request,
        cache,
        adapter,
    ))?;
    run_session(&request, (&python, &catalog), &session, &analyses_class)
}

/// The session request row, in the order the native session reads it.
fn session_request<'py>(
    request: &Bound<'py, PyAny>,
    python: &[Bound<'py, PyAny>],
    catalog: &Bound<'py, PyAny>,
    rules: Vec<(String, String)>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let profile: Bound<'py, PyAny> = request.getattr("inference_profile")?;
    let mut families: Vec<(String, Vec<_>)> = Vec::new();
    for item in request
        .getattr("dynamic_families_by_table")?
        .call_method0("items")?
        .try_iter()?
    {
        let (name, declared): (String, Bound<'py, PyAny>) = item?.extract()?;
        families.push((name, family_rows(&declared)?));
    }
    let items: Vec<Bound<'py, PyAny>> = vec![
        profile_dialect(&profile)?.into_bound_py_any(py)?,
        case_sensitive_shapes(&profile, &profile.getattr("sql_analysis_dialect")?)?
            .into_bound_py_any(py)?,
        return_types(&profile)?.into_bound_py_any(py)?,
        rules.into_bound_py_any(py)?,
        request.getattr("rich_type_inference")?,
        shape_rows(&request.getattr("column_types_by_table")?)?.into_bound_py_any(py)?,
        shape_rows(&request.getattr("column_nullability_by_table")?)?.into_bound_py_any(py)?,
        shape_rows(&request.getattr("complete_binding_schemas")?)?.into_bound_py_any(py)?,
        shape_rows(&catalog.getattr("schemas")?)?.into_bound_py_any(py)?,
        families.into_bound_py_any(py)?,
        model_rows(py, python)?,
    ];
    Ok(PyTuple::new(py, items)?.into_any())
}

/// The analysis store's path and environment, or None where Python bypasses its cache.
fn analysis_store<'py>(request: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let context: Bound<'py, PyAny> = request.getattr("analysis_cache")?;
    if context.is_none() {
        return Ok(py.None().into_bound(py));
    }
    let path: Bound<'py, PyAny> = context
        .getattr("root")?
        .div(STORE_FILE_NAME)?
        .str()?
        .into_any();
    let identity: Bound<'py, PyAny> = PyString::new(py, &current_code_identity(py)?).into_any();
    let parts: Bound<'py, PyList> = PyList::new(
        py,
        [
            PyString::new(py, STORE_VERSION).into_any(),
            identity,
            context.getattr("shared_fingerprint")?,
            context.getattr("signature_namespace")?,
        ],
    )?;
    let environment: Bound<'py, PyAny> =
        registry::native(py, NativeAttr::ContentDigest)?.call1((parts,))?;
    Ok(PyTuple::new(py, [path, environment])?.into_any())
}

/// Run and finish the session, leaving Python's catalog and metrics as its analysis did.
fn run_session<'py>(
    request: &Bound<'py, PyAny>,
    (python, catalog): (&[Bound<'py, PyAny>], &Bound<'py, PyAny>),
    session: &Bound<'py, PyAny>,
    analyses_class: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = request.py();
    let types: Bound<'py, PyDict> = copied(&request.getattr("column_types_by_table")?)?;
    let nullability: Bound<'py, PyDict> = copied(&request.getattr("column_nullability_by_table")?)?;
    let (publications, failures): (Bound<'py, PyAny>, Bound<'py, PyAny>) =
        session.call_method0("run")?.extract()?;
    for failure in failures.try_iter()? {
        log_debug(py, ANALYSIS_FAILURE_MESSAGE, &failure?)?;
    }
    let unknown: Bound<'py, PyAny> =
        registry::class(py, RecordId::InferredNullability)?.getattr("UNKNOWN")?;
    for item in publications.try_iter()? {
        let (name, shape): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        let published: Bound<'py, PyAny> = dict_of(&shape)?;
        types.call_method1("setdefault", (&name, &published))?;
        let defaults: Bound<'py, PyAny> = PyDict::new(py)
            .into_any()
            .getattr("fromkeys")?
            .call1((&published, &unknown))?;
        nullability.call_method1("setdefault", (&name, defaults))?;
    }
    let (additions, analysis_names, succeeded): (
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
        Bound<'py, PyAny>,
    ) = session.call_method0("finish")?.extract()?;
    record_catalog_changes(catalog, &additions, &analysis_names, (&types, &nullability))?;
    record_cache(python, session)?;
    let positions: Bound<'py, PyDict> = PyDict::new(py);
    let mut names: Vec<Bound<'py, PyAny>> = Vec::new();
    for model_input in python {
        let name: Bound<'py, PyAny> = model_input
            .getattr("model_file")?
            .getattr("file_path")?
            .getattr("stem")?;
        positions.set_item(&name, names.len())?;
        names.push(name);
    }
    let succeeded: Vec<bool> = succeeded.extract()?;
    let succeeded_names: Vec<&Bound<'py, PyAny>> = names
        .iter()
        .zip(&succeeded)
        .filter_map(|(name, success)| success.then_some(name))
        .collect();
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("positions", positions)?;
    arguments.set_item("succeeded", PyFrozenSet::new(py, succeeded_names)?)?;
    arguments.set_item("session", session)?;
    analyses_class.call((), Some(&arguments))
}

/// Leave Python's binding catalog as its own analysis would have.
fn record_catalog_changes<'py>(
    catalog: &Bound<'py, PyAny>,
    schema_additions: &Bound<'py, PyAny>,
    analysis_names: &Bound<'py, PyAny>,
    (types, nullability): (&Bound<'py, PyDict>, &Bound<'py, PyDict>),
) -> PyResult<()> {
    let py: Python<'py> = catalog.py();
    let schemas: Bound<'py, PyAny> = catalog.getattr("schemas")?;
    let additions: Bound<'py, PyDict> = PyDict::new(py);
    for item in schema_additions.try_iter()? {
        let (name, shape): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        if !schemas.contains(&name)? {
            additions.set_item(name, dict_of(&shape)?)?;
        }
    }
    schemas.call_method1("update", (&additions,))?;
    if !additions.is_empty() {
        catalog
            .getattr("native")?
            .call_method1("update_relations", (&additions,))?;
    }
    let selected_types: Bound<'py, PyDict> = PyDict::new(py);
    let selected_nullability: Bound<'py, PyDict> = PyDict::new(py);
    let names: Vec<Bound<'py, PyAny>> = analysis_names.try_iter()?.collect::<PyResult<_>>()?;
    for name in &names {
        if let Some(shape) = types.get_item(name)? {
            selected_types.set_item(name, shape)?;
        }
    }
    for name in &names {
        if let Some(shape) = nullability.get_item(name)? {
            selected_nullability.set_item(name, shape)?;
        }
    }
    let arguments: Bound<'py, PyDict> = PyDict::new(py);
    arguments.set_item("types", selected_types)?;
    arguments.set_item("nullability", selected_nullability)?;
    catalog
        .getattr("prepare_analysis")?
        .call((), Some(&arguments))?;
    Ok(())
}

fn record_cache(python: &[Bound<'_, PyAny>], session: &Bound<'_, PyAny>) -> PyResult<()> {
    let py: Python<'_> = session.py();
    let stats: Bound<'_, PyAny> = session.getattr("cache_stats")?;
    if stats.is_none() {
        return record_metrics(py, (0, 0, python.len()));
    }
    let (hits, misses, _, failure): (usize, usize, usize, Bound<'_, PyAny>) = stats.extract()?;
    if !failure.is_none() {
        log_debug(py, STORE_FAILURE_MESSAGE, &failure)?;
    }
    if hits + misses == 0 {
        return record_metrics(py, (0, 0, python.len()));
    }
    record_metrics(py, (hits, misses, 0))
}

/// Record the analysis cache entries a native session read, missed and bypassed.
fn record_metrics(
    _py: Python<'_>,
    (hits, misses, bypasses): (usize, usize, usize),
) -> PyResult<()> {
    record_analysis_cache_metrics((0, hits, misses, bypasses));
    Ok(())
}

/// Each model's native request row, in analysis order.
fn model_rows<'py>(
    py: Python<'py>,
    model_inputs: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let enforced: Bound<'py, PyAny> =
        registry::class(py, RecordId::ContractPolicy)?.getattr("ENFORCED")?;
    let snapshot: Bound<'py, PyAny> =
        registry::class(py, RecordId::MaterializationType)?.getattr("SNAPSHOT")?;
    let mut rows: Vec<Bound<'py, PyAny>> = Vec::with_capacity(model_inputs.len());
    for model_input in model_inputs {
        let values: Bound<'py, PyAny> = model_input.getattr("config")?.getattr("values")?;
        let get = |key: &str| values.call_method1("get", (key,));
        let query_sql: Bound<'py, PyAny> = PyString::new(
            py,
            &analysis_cursor_sql(
                py,
                &model_input.getattr("query_sql")?.extract::<String>()?,
                &get("cursor_type")?,
            )?,
        )
        .into_any();
        let mut placeholders: Vec<(String, String)> = Vec::new();
        let raw: Bound<'py, PyAny> = get("placeholders")?;
        if raw.is_instance_of::<PyDict>() {
            for item in raw.call_method0("items")?.try_iter()? {
                let (key, value): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
                placeholders.push((key.str()?.extract()?, value.str()?.extract()?));
            }
        }
        let mut references: Vec<(String, String)> = Vec::new();
        for row in model_input.getattr("reference_rows")?.try_iter()? {
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
            model_input
                .getattr("model_file")?
                .getattr("file_path")?
                .getattr("stem")?,
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

/// `dict(pairs)`.
fn dict_of<'py>(pairs: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let dict: Bound<'py, PyDict> = PyDict::new(pairs.py());
    for item in pairs.try_iter()? {
        let (key, value): (Bound<'py, PyAny>, Bound<'py, PyAny>) = item?.extract()?;
        dict.set_item(key, value)?;
    }
    Ok(dict.into_any())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(analyze_native_model_sql, module)?)
}
