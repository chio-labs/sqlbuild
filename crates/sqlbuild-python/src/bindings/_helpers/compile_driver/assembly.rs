//! Planner-ready project assembly: diagnostics collection, the macro bridge and explicit references.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyCFunction, PyDict, PyTuple};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::compile_driver::assembly_project::assembled_project;
use crate::bindings::_helpers::compile_driver::project::lineage_mode;
use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported, within,
};

const COLLECTOR_MODULE: &str = "sqlbuild.compiler.compile._helpers.diagnostics.collector";
const PROJECT_WITH_MODULE: &str = "sqlbuild.compiler.compiled_project.main.project_with";
const RECORD_ANALYSES_MODULE: &str =
    "sqlbuild.compiler.compiled_project.main._record_model_analyses";
const EXPLICIT_REFERENCES_MODULE: &str =
    "sqlbuild.compiler.compile._helpers.explicit_references.checks";
const ACTIVE_BRIDGE_MODULE: &str = "sqlbuild.compiler.macro_bridge.main.active_macro_bridge";
const RUN_BRIDGE_MODULE: &str = "sqlbuild.compiler.macro_bridge.main.run_with_macro_bridge";

const OPTIONAL: [&str; 5] = [
    "inference_profile",
    "skip_column_inference",
    "column_lineage_mode",
    "analysis_cache_dir",
    "analysis_model_names",
];

/// The keyword arguments of one project assembly.
pub(crate) struct AssemblyRequest {
    pub(crate) inputs: Py<PyAny>,
    pub(crate) inference_profile: Py<PyAny>,
    pub(crate) skip_column_inference: Py<PyAny>,
    pub(crate) column_lineage_mode: Py<PyAny>,
    pub(crate) analysis_cache_dir: Py<PyAny>,
    pub(crate) analysis_model_names: Py<PyAny>,
}

/// Convert compile inputs into the planner-ready project view.
#[pyfunction]
#[pyo3(signature = (**options))]
fn assemble_project<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let arguments: KeywordArguments<'py> =
        KeywordArguments::read(py, "assemble_project", options, (&["inputs"], &OPTIONAL))?;
    let request: AssemblyRequest = AssemblyRequest {
        inputs: arguments.value("inputs")?.unbind(),
        inference_profile: arguments.value("inference_profile")?.unbind(),
        skip_column_inference: arguments.value_or_false("skip_column_inference")?.unbind(),
        column_lineage_mode: lineage_mode(&arguments)?.unbind(),
        analysis_cache_dir: arguments.value("analysis_cache_dir")?.unbind(),
        analysis_model_names: arguments.value("analysis_model_names")?.unbind(),
    };
    let collector: Bound<'py, PyAny> =
        imported(py, COLLECTOR_MODULE, "collect_compile_diagnostics")?.call0()?;
    let (built, violations): (Bound<'py, PyAny>, Bound<'py, PyAny>) =
        within(&collector, |violations| {
            Ok((referenced_project(py, request)?, violations.clone()))
        })?;
    let collected: Bound<'py, PyAny> = violations.getattr("diagnostics")?;
    if !collected.is_truthy()? {
        return Ok(built);
    }
    let diagnostics: Bound<'py, PyTuple> = chained(&built.getattr("diagnostics")?, &collected)?;
    call_with(
        &imported(py, PROJECT_WITH_MODULE, "project_with")?,
        &[("project", built), ("diagnostics", diagnostics.into_any())],
    )
}

/// `first` followed by `second`, as one tuple.
pub(crate) fn chained<'py>(
    first: &Bound<'py, PyAny>,
    second: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    PyTuple::new(
        first.py(),
        first
            .try_iter()?
            .chain(second.try_iter()?)
            .collect::<PyResult<Vec<_>>>()?,
    )
}

/// The undecorated `assemble_project`.
fn referenced_project(py: Python<'_>, request: AssemblyRequest) -> PyResult<Bound<'_, PyAny>> {
    let inputs: Bound<'_, PyAny> = request.inputs.bind(py).clone();
    let project: Bound<'_, PyAny> = if imported(py, ACTIVE_BRIDGE_MODULE, "active_macro_bridge")?
        .call0()?
        .is_none()
    {
        let stage: Bound<'_, PyCFunction> = PyCFunction::new_closure(
            py,
            None,
            None,
            move |arguments: &Bound<'_, PyTuple>, _: Option<&Bound<'_, PyDict>>| {
                assembled_project(arguments.py(), &request).map(Bound::unbind)
            },
        )?;
        call_with(
            &imported(py, RUN_BRIDGE_MODULE, "run_with_macro_bridge")?,
            &[("stage", stage.into_any())],
        )?
    } else {
        assembled_project(py, &request)?
    };
    let project: Bound<'_, PyAny> =
        with_native_project(&project, &inputs.getattr("native_project")?)?;
    let references: Bound<'_, PyAny> = call_with(
        &imported(py, EXPLICIT_REFERENCES_MODULE, "explicit_reference_report")?,
        &[
            ("project", project.clone()),
            ("discovered_inputs", inputs.getattr("discovered_inputs")?),
            (
                "enforce_explicit",
                inputs
                    .getattr("project_config")?
                    .getattr("references")?
                    .getattr("enforce_explicit")?,
            ),
        ],
    )?;
    let reference_diagnostics: Bound<'_, PyAny> = references.getattr("diagnostics")?;
    let unmatched: Bound<'_, PyAny> = references.getattr("unmatched")?;
    if !reference_diagnostics.is_truthy()? && !unmatched.is_truthy()? {
        return Ok(project);
    }
    let diagnostics: Bound<'_, PyTuple> =
        chained(&project.getattr("diagnostics")?, &reference_diagnostics)?;
    call_with(
        &imported(py, PROJECT_WITH_MODULE, "project_with")?,
        &[
            ("project", project),
            ("diagnostics", diagnostics.into_any()),
            ("unmatched_literal_sql_relations", unmatched),
        ],
    )
}

/// Hand the compile's native project the assembled analyses and keep it on the project.
fn with_native_project<'py>(
    project: &Bound<'py, PyAny>,
    native_project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    if native_project.is_none() {
        return Ok(project.clone());
    }
    call_with(
        &imported(py, RECORD_ANALYSES_MODULE, "record_model_analyses")?,
        &[
            ("project", native_project.clone()),
            ("models", project.getattr("models")?),
        ],
    )?;
    if project.getattr("native_project")?.is(native_project) {
        return Ok(project.clone());
    }
    call_with(
        &imported(py, PROJECT_WITH_MODULE, "project_with")?,
        &[
            ("project", project.clone()),
            ("native_project", native_project.clone()),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(assemble_project, module)?)
}
