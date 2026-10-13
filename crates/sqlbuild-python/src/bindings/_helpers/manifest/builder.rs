//! `build_manifest`: the dbt-style manifest bytes, whose encoding error is raised on writing.

use pyo3::exceptions::{PyKeyError, PyRecursionError, PyTypeError, PyValueError};
use pyo3::prelude::{
    Bound, Py, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::PyBytes;
use pyo3::{FromPyObject, PyRef, pyclass, pyfunction, pymethods, wrap_pyfunction};
use sqlbuild_analysis::graph::models::ProjectGraph;
use sqlbuild_analysis::manifest::errors::{ManifestEncodeError, ManifestError};
use sqlbuild_analysis::manifest::main::build_manifest_json::build_manifest_json;
use sqlbuild_analysis::manifest::models::ManifestInput;
use sqlbuild_core::json::errors::JsonEmitError;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::graph::project_graph::NativeProjectGraph;
use crate::bindings::_helpers::manifest::rows::{
    ProjectRows, plan_input, project_rows, python_hooks,
};

const FINGERPRINT_EXCEPTIONS_MODULE: &str = "sqlbuild.compiler.fingerprints.exceptions";

/// A built manifest: its `manifest.json` bytes, or the error `json.dumps` raised encoding it.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeManifest {
    contents: Result<Vec<u8>, ManifestEncodeError>,
}

#[pymethods]
impl NativeManifest {
    /// The bytes `json.dumps(manifest, indent=2) + "\n"` encoded, raising what it raised.
    fn contents<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        match &self.contents {
            Ok(bytes) => Ok(PyBytes::new(py, bytes)),
            Err(ManifestEncodeError::Unencodable(message)) => {
                Err(PyTypeError::new_err(message.clone()))
            }
            Err(ManifestEncodeError::Emit(JsonEmitError::NestingTooDeep)) => Err(
                PyRecursionError::new_err("maximum recursion depth exceeded"),
            ),
            Err(ManifestEncodeError::Emit(error)) => {
                Err(PyValueError::new_err(format!("{error:?}")))
            }
        }
    }
}

fn python_error(error: ManifestError, py: Python<'_>) -> PyErr {
    match error {
        ManifestError::QueryFingerprint(message) => py
            .import(FINGERPRINT_EXCEPTIONS_MODULE)
            .and_then(|module| module.getattr("QueryFingerprintError"))
            .and_then(|class| class.call1((message,)))
            .map_or_else(|error| error, PyErr::from_value),
        ManifestError::MissingParameterType(name) => PyKeyError::new_err(name),
    }
}

/// The manifest facts only Python knows: names, the generation stamp and hook identities.
#[derive(FromPyObject)]
#[pyo3(from_item_all)]
pub(crate) struct ManifestFacts<'py> {
    project_name: String,
    adapter_type: String,
    /// `datetime.now(tz=UTC).isoformat()`.
    generated_at: String,
    /// `build_hook_identities(project.hook_functions)`.
    hook_identities: Bound<'py, PyAny>,
}

/// The manifest of `project` and the optional plan.
#[pyfunction]
#[pyo3(signature = (*, project, plan_output, graph, facts))]
pub(crate) fn build_manifest(
    project: &Bound<'_, PyAny>,
    plan_output: &Bound<'_, PyAny>,
    graph: PyRef<'_, NativeProjectGraph>,
    facts: ManifestFacts<'_>,
) -> PyResult<Py<NativeManifest>> {
    compiler_guard(|| {
        let py: Python<'_> = project.py();
        let ManifestFacts {
            project_name,
            adapter_type,
            generated_at,
            hook_identities,
        } = facts;
        let python_hooks = python_hooks(project, &hook_identities)?;
        let ProjectRows {
            run_id,
            sql_analysis_dialect,
            models,
            sources,
            seeds,
            macros,
            macro_declarations,
            sql_hooks,
        } = project_rows(project)?;
        let input: ManifestInput = ManifestInput {
            project_name,
            adapter_type,
            run_id,
            generated_at,
            sql_analysis_dialect,
            models,
            sources,
            seeds,
            macros,
            macro_declarations,
            sql_hooks,
            python_hooks,
            plan: plan_input(plan_output)?,
        };
        let graph: &ProjectGraph = graph.graph();
        let contents = py
            .detach(|| build_manifest_json(&input, graph))
            .map_err(|error| python_error(error, py))?
            .map(String::into_bytes);
        Py::new(py, NativeManifest { contents })
    })
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(build_manifest, module)?)?;
    module.add_class::<NativeManifest>()
}
