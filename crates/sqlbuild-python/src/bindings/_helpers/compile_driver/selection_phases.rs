//! Unit-test selector splitting, analysis and rule selection, and static command compilation.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyFrozenSet};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::python_calls::{call_with, imported, keywords};

const NATIVE_RECORDS_MODULE: &str = "sqlbuild._native";

const NATIVE_MODULE: &str = "sqlbuild._native";
const SPLIT_SELECTORS_MODULE: &str = "sqlbuild._native";
const PLANNER_SCOPES_MODULE: &str = "sqlbuild._native";
const STATIC_SCOPE_MODULE: &str = "sqlbuild._native";
const STATIC_RELATIONS_MODULE: &str = "sqlbuild._native";
const DATACLASSES_MODULE: &str = "dataclasses";

/// Whether a selection names nothing to select or exclude.
fn unselective(selection: &Bound<'_, PyAny>) -> PyResult<bool> {
    Ok(!selection.getattr("select")?.is_truthy()? && !selection.getattr("exclude")?.is_truthy()?)
}

/// Options whose selectors name only resources, with unit tests selected apart.
fn unit_test_selectors_applied<'py>(
    options: &Bound<'py, PyAny>,
    discovered: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let resolved: Bound<'py, PyAny> = if options.is_none() {
        imported(py, NATIVE_RECORDS_MODULE, "CompilePipelineOptions")?.call0()?
    } else {
        options.clone()
    };
    if unselective(&resolved)? {
        return Ok(resolved);
    }
    let split: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            SPLIT_SELECTORS_MODULE,
            "split_project_unit_test_selectors",
        )?,
        &[
            ("select", resolved.getattr("select")?),
            ("exclude", resolved.getattr("exclude")?),
            ("discovered_inputs", discovered.clone()),
            (
                "accepts_unit_tests",
                resolved.getattr("accepts_unit_test_selectors")?,
            ),
        ],
    )?;
    imported(py, DATACLASSES_MODULE, "replace")?.call(
        (resolved,),
        Some(&keywords(
            py,
            &[
                ("select", split.getattr("select")?),
                ("exclude", split.getattr("exclude")?),
                ("sql_test_selection", split.getattr("sql_test_selection")?),
            ],
        )?),
    )
}

/// The planner scopes `selection` resolves over `project`.
fn planner_scopes<'py>(
    project: &Bound<'py, PyAny>,
    selection: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    call_with(
        &imported(py, PLANNER_SCOPES_MODULE, "resolve_planner_scopes")?,
        &[
            ("project", project.clone()),
            (
                "selection",
                call_with(
                    &imported(py, NATIVE_RECORDS_MODULE, "PlannerSelection")?,
                    &[
                        ("select", selection.getattr("select")?),
                        ("exclude", selection.getattr("exclude")?),
                    ],
                )?,
            ),
            (
                "policies",
                call_with(
                    &imported(py, NATIVE_RECORDS_MODULE, "PlannerPolicies")?,
                    &[("auto_load_sources", selection.getattr("auto_load_sources")?)],
                )?,
            ),
        ],
    )
}

/// The stale-warning scope's models of `scopes`.
fn scoped_models<'py>(scopes: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    scopes
        .getattr("stale_warning_scope")?
        .getattr("models_by_name")
}

/// Return options whose selectors name only resources, with unit tests selected apart.
#[pyfunction]
#[pyo3(signature = (*, options, discovered_inputs))]
fn apply_unit_test_selectors<'py>(
    options: &Bound<'py, PyAny>,
    discovered_inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    unit_test_selectors_applied(options, discovered_inputs)
}

/// Align configured-rule subjects with models that received deep SQL analysis.
#[pyfunction]
#[pyo3(signature = (*, options, discovered_inputs, project))]
fn resolve_configured_rule_selection<'py>(
    options: &Bound<'py, PyAny>,
    discovered_inputs: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = options.py();
    if !options
        .getattr("sql_test_selection")?
        .getattr("models_selected")?
        .is_truthy()?
    {
        return Ok(PyFrozenSet::empty(py)?.into_any());
    }
    let selection: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_compile_analysis_selection")?,
        &[
            ("options", options.clone()),
            ("discovered_inputs", discovered_inputs.clone()),
        ],
    )?;
    if selection.is_none() || unselective(&selection)? {
        return Ok(py.None().into_bound(py));
    }
    let models: Bound<'py, PyAny> = scoped_models(&planner_scopes(project, &selection)?)?;
    let keys: Vec<Bound<'py, PyAny>> = models
        .call_method0("values")?
        .try_iter()?
        .map(|model| model?.getattr("key"))
        .collect::<PyResult<_>>()?;
    Ok(PyFrozenSet::new(py, keys)?.into_any())
}

/// Return the models selected for deep analysis, or None to analyse every model.
#[pyfunction]
#[pyo3(signature = (*, compile_inputs, inference_profile, selection))]
fn resolve_analysis_model_names<'py>(
    compile_inputs: &Bound<'py, PyAny>,
    inference_profile: &Bound<'py, PyAny>,
    selection: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = compile_inputs.py();
    if selection.is_none() || unselective(selection)? {
        return Ok(py.None().into_bound(py));
    }
    let structural_project: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "assemble_project")?,
        &[
            ("inputs", compile_inputs.clone()),
            ("inference_profile", inference_profile.clone()),
            (
                "skip_column_inference",
                pyo3::types::PyBool::new(py, true).to_owned().into_any(),
            ),
            ("analysis_model_names", PyFrozenSet::empty(py)?.into_any()),
        ],
    )?;
    let models: Bound<'py, PyAny> =
        scoped_models(&planner_scopes(&structural_project, selection)?)?;
    Ok(PyFrozenSet::new(py, models.try_iter()?.collect::<PyResult<Vec<_>>>()?)?.into_any())
}

/// Locations of the deferred target's relations, when the options defer to one.
fn deferred_locations<'py>(
    (discovered, adapter): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    options: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let defer_to: Bound<'py, PyAny> = options.getattr("defer_to")?;
    if defer_to.is_none() {
        return Ok(py.None().into_bound(py));
    }
    let deferred_target: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "resolve_deferred_target_config")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("defer_to", defer_to),
            (
                "current_target_name",
                project.getattr("effective_target_name")?,
            ),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_MODULE, "build_deferred_locations")?,
        &[
            ("project", project.clone()),
            ("deferred_target_config", deferred_target),
            ("effective_vars", project.getattr("effective_vars")?),
            ("default_schema", adapter.call_method0("default_schema")?),
            (
                "default_database",
                adapter.call_method0("default_database")?,
            ),
            (
                "render_qualified_name",
                adapter.getattr("render_qualified_name")?,
            ),
        ],
    )
}

/// Run canonical compile, selector, and relation phases without build planning.
#[pyfunction]
#[pyo3(signature = (**request))]
fn compile_static_command_context<'py>(
    request: Option<&Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let request: Request<'_, 'py> = Request::new("compile_static_command_context", request)?;
    let py: Python<'py> = request.py();
    let none = || py.None().into_bound(py);
    let discovered: Bound<'py, PyAny> = request.get("discovered_inputs")?;
    let adapter: Bound<'py, PyAny> = request.get("adapter")?;
    let options: Bound<'py, PyAny> =
        unit_test_selectors_applied(&request.get("options")?, &discovered)?;
    let mut selected_keys: Bound<'py, PyAny> =
        request.optional("selected_keys")?.unwrap_or_else(none);
    if selected_keys.is_none()
        && !options
            .getattr("sql_test_selection")?
            .getattr("models_selected")?
            .is_truthy()?
    {
        selected_keys = PyFrozenSet::empty(py)?.into_any();
    }
    let compiled: Bound<'py, PyAny> = call_with(
        &imported(py, NATIVE_MODULE, "compile_project_phase")?,
        &[
            ("discovered_inputs", discovered.clone()),
            ("adapter", adapter.clone()),
            ("options", options.clone()),
            (
                "on_progress",
                request.optional("on_progress")?.unwrap_or_else(none),
            ),
        ],
    )?;
    let project: Bound<'py, PyAny> = compiled.getattr("project")?;
    let deferred: Bound<'py, PyAny> =
        deferred_locations((&discovered, &adapter), &options, &project)?;
    let scope: Bound<'py, PyAny> = call_with(
        &imported(py, STATIC_SCOPE_MODULE, "resolve_static_command_scope")?,
        &[
            ("project", project.clone()),
            (
                "selection",
                call_with(
                    &imported(py, NATIVE_RECORDS_MODULE, "PlannerSelection")?,
                    &[
                        ("select", options.getattr("select")?),
                        ("exclude", options.getattr("exclude")?),
                        ("selected_keys", selected_keys),
                        ("sql_test_selection", options.getattr("sql_test_selection")?),
                    ],
                )?,
            ),
            ("auto_load_sources", options.getattr("auto_load_sources")?),
        ],
    )?;
    let relations: Bound<'py, PyAny> = call_with(
        &imported(
            py,
            STATIC_RELATIONS_MODULE,
            "resolve_static_relation_context",
        )?,
        &[
            ("project", project.clone()),
            ("adapter", adapter),
            ("scope", scope.clone()),
            (
                "deferral",
                call_with(
                    &imported(py, NATIVE_RECORDS_MODULE, "DeferralInputs")?,
                    &[
                        ("deferred_locations", deferred),
                        ("defer_sources_to", options.getattr("defer_sources_to")?),
                        (
                            "source_deferral_enabled",
                            options.getattr("source_deferral_enabled")?,
                        ),
                    ],
                )?,
            ),
            ("project_config", discovered.getattr("project_config")?),
            ("local_config", discovered.getattr("local_config")?),
            (
                "relation_keys",
                request.optional("relation_keys")?.unwrap_or_else(none),
            ),
        ],
    )?;
    call_with(
        &imported(py, NATIVE_RECORDS_MODULE, "StaticCommandContext")?,
        &[
            ("project", project),
            ("scope", scope),
            ("relations", relations),
            ("connection_config", compiled.getattr("connection_config")?),
            ("compile_seconds", compiled.getattr("compile_seconds")?),
        ],
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(apply_unit_test_selectors, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_configured_rule_selection, module)?)?;
    module.add_function(wrap_pyfunction!(resolve_analysis_model_names, module)?)?;
    module.add_function(wrap_pyfunction!(compile_static_command_context, module)?)?;
    Ok(())
}
