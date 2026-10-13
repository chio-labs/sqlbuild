//! Offline scope facts: the persistent cache, a compile-input build, or the tolerant index.

use std::path::PathBuf;

use pyo3::exceptions::{PyImportError, PyOSError, PyUnicodeError, PyValueError};
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};
use crate::bindings::_helpers::discovery::scope_snapshot::discover_scope_snapshot;
use crate::bindings::_helpers::scopes::scope_cache::{
    project_fingerprint, read_scope_index_cache, write_scope_index_cache,
};
use crate::bindings::_helpers::scopes::scope_tolerant::scope_tolerant_index;

const NATIVE_MODULE: &str = "sqlbuild._native";
const CACHE_DIRECTORY_MODULE: &str = "sqlbuild.compiler.frontier.main.compiler_cache_directory";
const SCOPE_CONSTANTS_MODULE: &str = "sqlbuild.compiler.scopes.constants";
const SQL_ANALYSIS_MODELS_MODULE: &str = "sqlbuild.compiler.sql_analysis.models";
const ADAPTER_NAME_MODULE: &str = "sqlbuild.spec.contracts.main.resolve_effective_adapter_name";
const COLLECTION_RENDERING_MODULE: &str =
    "sqlbuild.spec.contracts.main.resolve_effective_collection_rendering";
const RESOLVE_ADAPTER_MODULE: &str = "sqlbuild.adapter.discovery.main.resolve_adapter";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const COMPILE_CONSTANTS_MODULE: &str = "sqlbuild.compiler.compile.constants";
const FRONTIER_TYPES_MODULE: &str = "sqlbuild.compiler.frontier.types";
const COMPILE_USAGES_MODULE: &str =
    "sqlbuild.compiler.compile.main._scope_index_with_compile_usages";
const MACRO_INVENTORY_MODULE: &str = "sqlbuild.compiler.compile.main._static_macro_inventory";

/// Where the scope index cache file of a project lives: `(directory, file name)`.
fn cache_location(project_dir: &Bound<'_, PyAny>) -> PyResult<(PathBuf, String)> {
    let py: Python<'_> = project_dir.py();
    let directory: Bound<'_, PyAny> =
        imported(py, CACHE_DIRECTORY_MODULE, "compiler_cache_directory")?
            .call1((project_dir,))?
            .div(imported(
                py,
                SCOPE_CONSTANTS_MODULE,
                "SCOPE_CACHE_DIRECTORY_NAME",
            )?)?;
    Ok((
        directory.extract()?,
        imported(py, SCOPE_CONSTANTS_MODULE, "SCOPE_CACHE_FILENAME")?.extract()?,
    ))
}

/// Whether `error` is a project input error that selects the tolerant index.
fn is_project_input_error(py: Python<'_>, error: &PyErr) -> bool {
    error.is_instance_of::<PyOSError>(py)
        || error.is_instance_of::<PyUnicodeError>(py)
        || error.is_instance_of::<PyValueError>(py)
        || error.is_instance_of::<PyImportError>(py)
}

/// The discovered project inputs and the project adapter that compiles them.
fn project_adapter<'py>(
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let py: Python<'py> = project_dir.py();
    let discover_keywords: Bound<'py, PyDict> = PyDict::new(py);
    discover_keywords.set_item("project_dir", project_dir)?;
    discover_keywords.set_item("extract_output_column_locations", false)?;
    let discovered: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "discover_project_inputs")?
        .call((), Some(&discover_keywords))?;
    let adapter_name: Bound<'py, PyAny> = call_with(
        &imported(py, ADAPTER_NAME_MODULE, "resolve_effective_adapter_name")?,
        &[
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
        ],
    )?;
    let adapter: Bound<'py, PyAny> = call_with(
        &imported(py, RESOLVE_ADAPTER_MODULE, "resolve_adapter")?,
        &[("adapter_name", adapter_name)],
    )?;
    Ok((discovered, adapter))
}

/// The compile inputs' canonical index with usage and placement facts.
fn compiled_index<'py>(
    discovered: Bound<'py, PyAny>,
    adapter: &Bound<'py, PyAny>,
    syntax: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let project_config: Bound<'py, PyAny> = discovered.getattr("project_config")?;
    let collection_rendering: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            COLLECTION_RENDERING_MODULE,
            "resolve_effective_collection_rendering",
        )?,
        &[
            ("project_config", project_config),
            ("declaration_override", py.None().into_bound(py)),
        ],
    )?;
    let adapter_context: Bound<'py, PyAny> = call_with(
        &imported(py, COMPILE_MODELS_MODULE, "CompileAdapterContext")?,
        &[
            ("value_renderer", adapter.clone()),
            ("collection_rendering", collection_rendering),
            (
                "python_functions_inherit_default_namespace",
                adapter.call_method0("python_functions_inherit_default_namespace")?,
            ),
            ("sql_lexical_syntax", syntax.clone()),
        ],
    )?;
    let stage_keywords: Bound<'py, PyDict> = PyDict::new(py);
    stage_keywords.set_item("discovered_inputs", discovered)?;
    stage_keywords.set_item("adapter_context", adapter_context)?;
    stage_keywords.set_item("resolved_connection", PyDict::new(py))?;
    stage_keywords.set_item("no_sql_validation", true)?;
    stage_keywords.set_item("defer_model_sql_validation", true)?;
    stage_keywords.set_item("no_cache", true)?;
    let python_stage: Bound<'py, PyAny> = py.import("functools")?.getattr("partial")?.call(
        (imported(py, NATIVE_MODULE, "build_compile_inputs")?,),
        Some(&stage_keywords),
    )?;
    let compile_inputs: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "compile_frontier")?,
        &[
            (
                "until",
                imported(py, FRONTIER_TYPES_MODULE, "CompilerStage")?
                    .getattr("COMPILE_PROJECT_INPUTS")?,
            ),
            ("python_stage", python_stage),
        ],
    )?;
    call_with(
        &imported(py, COMPILE_USAGES_MODULE, "scope_index_with_compile_usages")?,
        &[("inputs", compile_inputs)],
    )
}

/// The partial static index of tolerant discovery, with its faults as diagnostics.
fn tolerant_index<'py>(
    project_dir: &Bound<'py, PyAny>,
    syntax: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let snapshot: Bound<'py, PyAny> = discover_scope_snapshot(project_dir)?;
    let discovered: Bound<'py, PyAny> = snapshot.getattr("discovered_inputs")?;
    let inventory: Bound<'py, PyAny> = call_with(
        &imported(py, MACRO_INVENTORY_MODULE, "inventory_project_macros")?,
        &[("macro_files", discovered.getattr("macro_files")?)],
    )?;
    let native: Bound<'py, PyAny> = imported(py, NATIVE_MODULE, "open_native_scope_index")?
        .call1((&discovered, PyDict::new(py), inventory.getattr("exports")?))?;
    let scan_store: Bound<'py, PyTuple> = PyTuple::new(
        py,
        [
            py.None().into_bound(py),
            imported(
                py,
                COMPILE_CONSTANTS_MODULE,
                "SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM",
            )?,
        ],
    )?;
    let relationship_faults: Bound<'py, PyAny> = call_with(
        &native.getattr("grant_relationships")?,
        &[
            ("discovered_inputs", discovered),
            ("syntax", syntax.clone()),
            ("scan_store", scan_store.into_any()),
        ],
    )?;
    Ok(scope_tolerant_index(
        py,
        &native.call_method0("index_with_relationships")?,
        &snapshot,
        (inventory.getattr("faults")?, relationship_faults),
    )?
    .into_bound(py))
}

/// Load or build scope facts without credentials, a connection, or warehouse access.
#[pyfunction]
#[pyo3(signature = (*, project_dir, no_cache=false))]
fn load_or_build_scope_index<'py>(
    project_dir: &Bound<'py, PyAny>,
    no_cache: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project_dir.py();
    let resolved: Bound<'py, PyAny> = project_dir.call_method0("resolve")?;
    let fingerprint: Option<String> = project_fingerprint(py, resolved.extract()?)?;
    let cached_fingerprint: Option<&String> = fingerprint.as_ref().filter(|_| !no_cache);
    if let Some(fingerprint) = cached_fingerprint {
        let (directory, file_name) = cache_location(&resolved)?;
        if let Some(cached) =
            read_scope_index_cache(py, directory.join(file_name), fingerprint.clone())?
        {
            return Ok(cached.into_bound(py));
        }
    }
    let mut syntax: Bound<'py, PyAny> =
        imported(py, SQL_ANALYSIS_MODELS_MODULE, "SqlLexicalSyntax")?.call0()?;
    let compiled: PyResult<Bound<'py, PyAny>> = match project_adapter(&resolved) {
        Ok((discovered, adapter)) => {
            syntax = adapter.getattr("sql_lexical_syntax")?;
            compiled_index(discovered, &adapter, &syntax)
        }
        Err(error) => Err(error),
    };
    let index: Bound<'py, PyAny> = match compiled {
        Ok(index) => index,
        Err(error) if is_project_input_error(py, &error) => tolerant_index(&resolved, &syntax)?,
        Err(error) => return Err(error),
    };
    if let Some(fingerprint) = cached_fingerprint {
        let _ =
            write_scope_index_cache(py, cache_location(&resolved)?, fingerprint.clone(), &index)?;
    }
    Ok(index)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(load_or_build_scope_index, module)?)
}
