//! One compile's native model analysis session, with Python's catalog and metric bookkeeping.

use pyo3::IntoPyObjectExt;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyFrozenSet, PyList, PyString, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::analysis_session::profile_inputs::{
    case_sensitive_shapes, nullability_rules, profile_dialect, return_types, shape_rows,
};
use crate::bindings::_helpers::analysis_session::stage_functions::family_rows;
use crate::bindings::_helpers::boundary::keyword_request::Request;

const NATIVE_MODULE: &str = "sqlbuild._native";
const ANALYSIS_MODELS_MODULE: &str = "sqlbuild.compiler.analysis_session.models";
const PYTHON_ANALYSIS_MODULE: &str = "sqlbuild.compiler.compile.classes.python_model_analysis";
const LINEAGE_TYPES_MODULE: &str = "sqlbuild.compiler.lineage.types";
const CODE_IDENTITY_MODULE: &str = "sqlbuild.compiler.frontier.main.compiled_code_identity";
const LOG_DEBUG_MODULE: &str = "sqlbuild.diagnostics.main.log_debug_event";
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
    let analyses_class: Bound<'py, PyAny> = py
        .import(ANALYSIS_MODELS_MODULE)?
        .getattr("NativeModelAnalyses")?;
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
    let python: Bound<'py, PyAny> = {
        let arguments: Bound<'py, PyDict> = PyDict::new(py);
        arguments.set_item("model_inputs", &model_inputs)?;
        arguments.set_item("inference_profile", &profile)?;
        arguments.set_item(
            "complete_binding_schemas",
            request.getattr("complete_binding_schemas")?,
        )?;
        py.import(PYTHON_ANALYSIS_MODULE)?
            .getattr("PythonModelAnalysis")?
            .call((), Some(&arguments))?
    };
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
    let session: Bound<'py, PyAny> = py
        .import(NATIVE_MODULE)?
        .getattr("start_model_analysis_session")?
        .call1((catalog.getattr("native")?, session_request, cache, adapter))?;
    run_session(&request, (&python, &catalog), &session, &analyses_class)
}

/// The session request row, in the order the native session reads it.
fn session_request<'py>(
    request: &Bound<'py, PyAny>,
    python: &Bound<'py, PyAny>,
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
        python.call_method0("model_rows")?,
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
    let identity: Bound<'py, PyAny> = py
        .import(CODE_IDENTITY_MODULE)?
        .getattr("compiled_code_identity")?
        .call0()?;
    let parts: Bound<'py, PyList> = PyList::new(
        py,
        [
            PyString::new(py, STORE_VERSION).into_any(),
            identity,
            context.getattr("shared_fingerprint")?,
            context.getattr("signature_namespace")?,
        ],
    )?;
    let environment: Bound<'py, PyAny> = py
        .import(NATIVE_MODULE)?
        .getattr("content_digest")?
        .call1((parts,))?;
    Ok(PyTuple::new(py, [path, environment])?.into_any())
}

/// Run and finish the session, leaving Python's catalog and metrics as its analysis did.
fn run_session<'py>(
    request: &Bound<'py, PyAny>,
    (python, catalog): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
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
    let unknown: Bound<'py, PyAny> = py
        .import(LINEAGE_TYPES_MODULE)?
        .getattr("InferredNullability")?
        .getattr("UNKNOWN")?;
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
    for analysed in python.getattr("requests")?.try_iter()? {
        let name: Bound<'py, PyAny> = analysed?
            .getattr("model_input")?
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

fn record_cache(python: &Bound<'_, PyAny>, session: &Bound<'_, PyAny>) -> PyResult<()> {
    let stats: Bound<'_, PyAny> = session.getattr("cache_stats")?;
    if stats.is_none() {
        python.call_method0("record_uncached")?;
        return Ok(());
    }
    let (hits, misses, _, failure): (
        Bound<'_, PyAny>,
        Bound<'_, PyAny>,
        Bound<'_, PyAny>,
        Bound<'_, PyAny>,
    ) = stats.extract()?;
    if !failure.is_none() {
        log_debug(python.py(), STORE_FAILURE_MESSAGE, &failure)?;
    }
    if hits.add(&misses)?.eq(0)? {
        python.call_method0("record_uncached")?;
        return Ok(());
    }
    let arguments: Bound<'_, PyDict> = PyDict::new(python.py());
    arguments.set_item("hits", hits)?;
    arguments.set_item("misses", misses)?;
    python
        .getattr("record_cached")?
        .call((), Some(&arguments))?;
    Ok(())
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
    py.import(LOG_DEBUG_MODULE)?
        .getattr("log_debug_event")?
        .call((), Some(&arguments))?;
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
