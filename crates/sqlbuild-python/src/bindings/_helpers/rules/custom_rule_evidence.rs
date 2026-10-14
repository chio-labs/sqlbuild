//! Custom-rule import closures, implementation fingerprints and statically found test cases.

use std::path::PathBuf;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::PyTuple;
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_pysource::rule_evidence::main::implementation_fingerprint::implementation_fingerprint;
use sqlbuild_pysource::rule_evidence::main::import_closure::import_closure as import_closure_of;
use sqlbuild_pysource::rule_evidence::main::test_evidence::test_evidence;
use sqlbuild_pysource::rule_evidence::models::RuleTestEvidence;

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const PATHLIB_MODULE: &str = "pathlib";
const INSPECT_MODULE: &str = "inspect";
const HASHLIB_MODULE: &str = "hashlib";

fn python_version(py: Python<'_>) -> (u8, u8) {
    let version = py.version_info();
    (version.major, version.minor)
}

/// `Path(rule.source).resolve()` as a Python path, or `None` for a rule without a source file.
fn resolved_source<'py>(rule: &Bound<'py, PyAny>) -> PyResult<Option<Bound<'py, PyAny>>> {
    let source: Bound<'py, PyAny> = rule.getattr("source")?;
    if source.is_none() {
        return Ok(None);
    }
    let path: Bound<'py, PyAny> = imported(rule.py(), PATHLIB_MODULE, "Path")?.call1((source,))?;
    path.call_method0("resolve").map(Some)
}

fn native_path(path: &Bound<'_, PyAny>) -> PyResult<PathBuf> {
    path.extract()
}

fn closure_paths<'py>(py: Python<'py>, paths: Vec<PathBuf>) -> PyResult<Bound<'py, PyTuple>> {
    let class: Bound<'py, PyAny> = imported(py, PATHLIB_MODULE, "Path")?;
    let paths: Vec<Bound<'py, PyAny>> = paths
        .into_iter()
        .map(|path| class.call1((path,)))
        .collect::<PyResult<_>>()?;
    PyTuple::new(py, paths)
}

/// Repository-owned helper files imported by one rule module.
#[pyfunction]
#[pyo3(signature = (*, rule, project_dir))]
fn custom_rule_import_closure<'py>(
    rule: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let py: Python<'py> = rule.py();
    let Some(source) = resolved_source(rule)? else {
        return Ok(PyTuple::empty(py));
    };
    let root: PathBuf = native_path(&project_dir.call_method0("resolve")?)?;
    let closure: Vec<PathBuf> =
        import_closure_of(&native_path(&source)?, &root, python_version(py));
    closure_paths(py, closure)
}

/// One rule's source file and helper closure fingerprint, or its check's source digest.
#[pyfunction]
#[pyo3(signature = (*, rule, project_dir, import_closure = None))]
pub(crate) fn custom_rule_implementation_fingerprint(
    rule: &Bound<'_, PyAny>,
    project_dir: &Bound<'_, PyAny>,
    import_closure: Option<&Bound<'_, PyAny>>,
) -> PyResult<String> {
    let py: Python<'_> = rule.py();
    let Some(source) = resolved_source(rule)? else {
        let text: Bound<'_, PyAny> =
            imported(py, INSPECT_MODULE, "getsource")?.call1((rule.getattr("check")?,))?;
        return imported(py, HASHLIB_MODULE, "sha256")?
            .call1((text.call_method0("encode")?,))?
            .call_method0("hexdigest")?
            .extract();
    };
    let root: PathBuf = native_path(&project_dir.call_method0("resolve")?)?;
    let source: PathBuf = native_path(&source)?;
    let closure: Vec<PathBuf> = match import_closure {
        Some(closure) if !closure.is_none() => closure
            .try_iter()?
            .map(|path| native_path(&path?))
            .collect::<PyResult<_>>()?,
        _ => import_closure_of(&source, &root, python_version(py)),
    };
    Ok(implementation_fingerprint(&source, &closure, &root)?)
}

/// `(path, line, column, owner)` of each public-harness case that statically evaluates the rule.
#[pyfunction]
#[pyo3(signature = (*, rule, project_dir))]
fn custom_rule_test_evidence<'py>(
    rule: &Bound<'py, PyAny>,
    project_dir: &Bound<'py, PyAny>,
) -> PyResult<Vec<(String, usize, usize, String)>> {
    let py: Python<'py> = rule.py();
    let Some(source) = resolved_source(rule)? else {
        return Ok(Vec::new());
    };
    let root_path: Bound<'py, PyAny> = project_dir.call_method0("resolve")?;
    let check_name: String = match rule.getattr("check")?.getattr("__name__") {
        Ok(name) => name.extract()?,
        Err(_) => String::new(),
    };
    let Some(evidence) = test_evidence(
        (&native_path(&source)?, &check_name),
        (&native_path(project_dir)?, &native_path(&root_path)?),
        python_version(py),
    ) else {
        source.call_method1("relative_to", (root_path,))?;
        return Ok(Vec::new());
    };
    Ok(evidence
        .into_iter()
        .map(|item: RuleTestEvidence| (item.path, item.line, item.column, item.owner))
        .collect())
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(custom_rule_import_closure, module)?)?;
    module.add_function(wrap_pyfunction!(
        custom_rule_implementation_fingerprint,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(custom_rule_test_evidence, module)?)?;
    Ok(())
}
