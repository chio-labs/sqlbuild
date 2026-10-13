//! The process-local declaration scope of one compile invocation.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::pyfunction;
use pyo3::types::PyTuple;

use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported};

const NATIVE_MODULE: &str = "sqlbuild._native";
const SCAN_CACHE_MODULE: &str = "sqlbuild.compiler.compile.classes.sql_test_scan_cache";
const COMPILE_CONSTANTS_MODULE: &str = "sqlbuild.compiler.compile.constants";
const COMPILE_ERRORS_MODULE: &str = "sqlbuild.compiler.compile.exceptions";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const DECLARATIONS_MODULE: &str = "sqlbuild.compiler.compile._helpers.render.declarations";
const SCOPE_ERRORS_MODULE: &str = "sqlbuild.compiler.scopes.exceptions";
const OPEN_INDEX_MODULE: &str = "sqlbuild.compiler.scopes.main._open_native_scope_index";
const VALIDATE_INDEX_MODULE: &str = "sqlbuild.compiler.scopes.main._validate_scope_index";

fn compile_error(py: Python<'_>, message: Bound<'_, PyAny>) -> PyResult<PyErr> {
    Ok(PyErr::from_value(
        imported(py, COMPILE_ERRORS_MODULE, "CompileInputError")?.call1((message,))?,
    ))
}

/// The declaration scope of `index`, resolved for `loaded_macros`.
fn scope_build<'py>(
    discovered: &Bound<'py, PyAny>,
    loaded_macros: &Bound<'py, PyAny>,
    (index, lookup, scan_cache): (Bound<'py, PyAny>, Bound<'py, PyAny>, Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let resolver: Bound<'py, PyAny> = call_with(
        &imported(py, DECLARATIONS_MODULE, "build_declaration_scope_resolver")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("scope_index", index.clone()),
            ("loaded_macros", loaded_macros.clone()),
            ("lookup", lookup),
        ],
    )?;
    call_with(
        &imported(py, COMPILE_MODELS_MODULE, "DeclarationScopeBuild")?,
        &[
            ("loaded_macros", loaded_macros.clone()),
            ("index", index),
            ("resolver", resolver),
            ("sql_test_scans", scan_cache),
        ],
    )
}

/// Build one canonical index and validate it before SQL expansion.
#[pyfunction]
#[pyo3(signature = (*, discovered_inputs, loaded_macros, sql_lexical_syntax, compile_cache_dir=None))]
pub(crate) fn build_declaration_scope<'py>(
    discovered_inputs: &Bound<'py, PyAny>,
    loaded_macros: &Bound<'py, PyAny>,
    sql_lexical_syntax: &Bound<'py, PyAny>,
    compile_cache_dir: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered_inputs.py();
    let scan_cache: Bound<'py, PyAny> = call_with(
        &imported(py, SCAN_CACHE_MODULE, "SqlTestScanCache")?,
        &[(
            "cache_dir",
            compile_cache_dir.unwrap_or_else(|| py.None().into_bound(py)),
        )],
    )?;
    let test_files: Bound<'py, PyAny> = discovered_inputs.getattr("test_files")?;
    let scenario_files: Bound<'py, PyAny> = discovered_inputs.getattr("scenario_files")?;
    imported(py, NATIVE_MODULE, "validate_authored_sql_test_ctes")?.call1((
        &test_files,
        &scenario_files,
        sql_lexical_syntax.getattr("native_mapping")?,
    ))?;
    let native: Bound<'py, PyAny> = call_with(
        &imported(py, OPEN_INDEX_MODULE, "open_native_scope_index")?,
        &[
            ("discovered_inputs", discovered_inputs.clone()),
            ("loaded_macros", loaded_macros.clone()),
        ],
    )?;
    let validated: PyResult<Bound<'py, PyAny>> = call_with(
        &imported(py, VALIDATE_INDEX_MODULE, "validate_scope_index")?,
        &[("index", native.getattr("index")?)],
    );
    if let Err(error) = validated {
        if !error.is_instance(
            py,
            &imported(py, SCOPE_ERRORS_MODULE, "ScopeValidationError")?,
        ) {
            return Err(error);
        }
        let raised: PyErr = compile_error(py, error.value(py).str()?.into_any())?;
        raised.set_cause(py, Some(error));
        return Err(raised);
    }
    if native
        .getattr("has_scoped_relationship_declarations")?
        .is_truthy()?
        && (test_files.is_truthy()? || scenario_files.is_truthy()?)
    {
        let faults: Bound<'py, PyAny> = call_with(
            &native.getattr("grant_relationships")?,
            &[
                ("discovered_inputs", discovered_inputs.clone()),
                ("syntax", sql_lexical_syntax.clone()),
                (
                    "scan_store",
                    PyTuple::new(
                        py,
                        [
                            scan_cache.call_method0("opened")?,
                            imported(
                                py,
                                COMPILE_CONSTANTS_MODULE,
                                "SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM",
                            )?,
                        ],
                    )?
                    .into_any(),
                ),
            ],
        )?;
        if faults.is_truthy()? {
            return Err(compile_error(py, faults.get_item(0)?.get_item(1)?)?);
        }
    }
    let index: Bound<'py, PyAny> = native.call_method0("index_with_relationships")?;
    let lookup: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "build_scope_lookup")?.call1((&index,))?;
    scope_build(
        discovered_inputs,
        loaded_macros,
        (index, lookup, scan_cache),
    )
}

/// Each loaded macro's metadata that the built index recorded.
fn indexed_macro_metadata<'py>(loaded_macros: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = loaded_macros.py();
    let code_type: Bound<'py, PyAny> = imported(py, "types", "CodeType")?;
    let signature: Bound<'py, PyAny> = imported(py, "inspect", "signature")?;
    let mut rows: Vec<Bound<'py, PyTuple>> = Vec::new();
    for pair in loaded_macros.call_method0("items")?.try_iter()? {
        let (key, loaded): (Bound<'py, PyAny>, Bound<'py, PyAny>) = pair?.extract()?;
        let function: Bound<'py, PyAny> = loaded.getattr("function")?;
        let code: Bound<'py, PyAny> =
            imported(py, "builtins", "getattr")?.call1((&function, "__code__", py.None()))?;
        let first_line: Bound<'py, PyAny> = if code.is_instance(&code_type)? {
            code.getattr("co_firstlineno")?
        } else {
            py.None().into_bound(py)
        };
        let parameters: Bound<'py, PyTuple> = PyTuple::new(
            py,
            signature
                .call1((&function,))?
                .getattr("parameters")?
                .try_iter()?
                .collect::<PyResult<Vec<_>>>()?,
        )?;
        rows.push(PyTuple::new(
            py,
            [
                key,
                loaded.getattr("name")?,
                loaded.getattr("relative_path")?,
                loaded.getattr("raw_source")?,
                loaded.getattr("dependencies")?,
                first_line,
                parameters.into_any(),
            ],
        )?);
    }
    PyTuple::new(py, rows)
}

/// Pair a built index with private macro instances, or return None if their metadata differs.
#[pyfunction]
#[pyo3(signature = (*, scope, discovered_inputs, loaded_macros))]
pub(crate) fn rebind_declaration_scope<'py>(
    scope: &Bound<'py, PyAny>,
    discovered_inputs: &Bound<'py, PyAny>,
    loaded_macros: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = scope.py();
    let current: Bound<'py, PyTuple> = indexed_macro_metadata(loaded_macros)?;
    let indexed: Bound<'py, PyTuple> = indexed_macro_metadata(&scope.getattr("loaded_macros")?)?;
    if current.as_any().ne(indexed.as_any())? {
        return Ok(py.None().into_bound(py));
    }
    scope_build(
        discovered_inputs,
        loaded_macros,
        (
            scope.getattr("index")?,
            scope.getattr("resolver")?.getattr("lookup")?,
            scope.getattr("sql_test_scans")?,
        ),
    )
}
