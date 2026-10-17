//! Unit-test selector splitting, analysis and rule selection, and static command compilation.

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PyFrozenSet};
use pyo3::{pyfunction, wrap_pyfunction};

use crate::bindings::_helpers::boundary::keyword_request::Request;
use crate::bindings::_helpers::compile_driver::assembly::assemble_project;
use crate::bindings::_helpers::compile_driver::deferral::{
    build_deferred_locations, resolve_deferred_target_config,
};
use crate::bindings::_helpers::compile_driver::pipeline::compile_project_phase;
use crate::bindings::_helpers::compile_driver::pipeline_entries::compile_analysis_selection;
use crate::bindings::_helpers::compile_driver::python_calls::{imported, keywords};
use crate::bindings::_helpers::planner_entries::command_plans::{
    resolve_static_command_scope, resolve_static_relation_context,
};
use crate::bindings::_helpers::planner_phases::scopes::resolve_planner_scopes;
use crate::bindings::_helpers::planner_selection::unit_tests::split_project_unit_test_selectors;
use crate::bindings::_helpers::records::construct::{new_record, new_record_with};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_values;
use crate::bindings::_helpers::records::ids::RecordId;

const DATACLASSES_MODULE: &str = "dataclasses";

/// Whether a selection names nothing to select or exclude.
fn unselective(selection: &Bound<'_, PyAny>) -> PyResult<bool> {
    Ok(!native_field(selection, "select")?.is_truthy()?
        && !native_field(selection, "exclude")?.is_truthy()?)
}

/// Options whose selectors name only resources, with unit tests selected apart.
fn unit_test_selectors_applied<'py>(
    options: &Bound<'py, PyAny>,
    discovered: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = discovered.py();
    let resolved: Bound<'py, PyAny> = if options.is_none() {
        new_record(py, RecordId::CompilePipelineOptions, (), None)?
    } else {
        options.clone()
    };
    if unselective(&resolved)? {
        return Ok(resolved);
    }
    let split: Bound<'py, PyAny> = split_project_unit_test_selectors(
        &native_field(&resolved, "select")?,
        &native_field(&resolved, "exclude")?,
        discovered,
        native_field(&resolved, "accepts_unit_test_selectors")?.extract()?,
    )?;
    imported(py, DATACLASSES_MODULE, "replace")?.call(
        (resolved,),
        Some(&keywords(
            py,
            &[
                ("select", native_field(&split, "select")?),
                ("exclude", native_field(&split, "exclude")?),
                (
                    "sql_test_selection",
                    native_field(&split, "sql_test_selection")?,
                ),
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
    resolve_planner_scopes(
        project,
        &new_record_with(
            py,
            RecordId::PlannerSelection,
            &[
                ("select", native_field(selection, "select")?),
                ("exclude", native_field(selection, "exclude")?),
            ],
        )?,
        &new_record_with(
            py,
            RecordId::PlannerPolicies,
            &[(
                "auto_load_sources",
                native_field(selection, "auto_load_sources")?,
            )],
        )?,
    )
}

/// The stale-warning scope's models of `scopes`.
fn scoped_models<'py>(scopes: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    native_field(scopes, "stale_warning_scope")?.getattr("models_by_name")
}

/// Return options whose selectors name only resources, with unit tests selected apart.
#[pyfunction]
#[pyo3(signature = (*, options, discovered_inputs))]
pub(crate) fn apply_unit_test_selectors<'py>(
    options: &Bound<'py, PyAny>,
    discovered_inputs: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    unit_test_selectors_applied(options, discovered_inputs)
}

/// Align configured-rule subjects with models that received deep SQL analysis.
#[pyfunction]
#[pyo3(signature = (*, options, discovered_inputs, project))]
pub(crate) fn resolve_configured_rule_selection<'py>(
    options: &Bound<'py, PyAny>,
    discovered_inputs: &Bound<'py, PyAny>,
    project: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = options.py();
    if !native_field(options, "sql_test_selection")?
        .getattr("models_selected")?
        .is_truthy()?
    {
        return Ok(PyFrozenSet::empty(py)?.into_any());
    }
    let selection: Bound<'py, PyAny> = compile_analysis_selection(options, discovered_inputs)?;
    if selection.is_none() || unselective(&selection)? {
        return Ok(py.None().into_bound(py));
    }
    let models: Bound<'py, PyAny> = scoped_models(&planner_scopes(project, &selection)?)?;
    let keys: Vec<Bound<'py, PyAny>> = mapping_values(&models)?
        .try_iter()?
        .map(|model| native_field(&model?, "key"))
        .collect::<PyResult<_>>()?;
    Ok(PyFrozenSet::new(py, keys)?.into_any())
}

/// Return the models selected for deep analysis, or None to analyse every model.
#[pyfunction]
#[pyo3(signature = (*, compile_inputs, inference_profile, selection))]
pub(crate) fn resolve_analysis_model_names<'py>(
    compile_inputs: &Bound<'py, PyAny>,
    inference_profile: &Bound<'py, PyAny>,
    selection: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = compile_inputs.py();
    if selection.is_none() || unselective(selection)? {
        return Ok(py.None().into_bound(py));
    }
    let structural_project: Bound<'py, PyAny> = assemble_project(
        py,
        Some(keywords(
            py,
            &[
                ("inputs", compile_inputs.clone()),
                ("inference_profile", inference_profile.clone()),
                (
                    "skip_column_inference",
                    pyo3::types::PyBool::new(py, true).to_owned().into_any(),
                ),
                ("analysis_model_names", PyFrozenSet::empty(py)?.into_any()),
            ],
        )?),
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
    let defer_to: Bound<'py, PyAny> = native_field(options, "defer_to")?;
    if defer_to.is_none() {
        return Ok(py.None().into_bound(py));
    }
    let deferred_target: Bound<'py, PyAny> = resolve_deferred_target_config(
        py,
        Some(keywords(
            py,
            &[
                ("discovered_inputs", discovered.clone()),
                ("defer_to", defer_to),
                (
                    "current_target_name",
                    native_field(project, "effective_target_name")?,
                ),
            ],
        )?),
    )?;
    Ok(build_deferred_locations(
        py,
        Some(keywords(
            py,
            &[
                ("project", project.clone()),
                ("deferred_target_config", deferred_target),
                ("effective_vars", native_field(project, "effective_vars")?),
                ("default_schema", adapter.call_method0("default_schema")?),
                (
                    "default_database",
                    adapter.call_method0("default_database")?,
                ),
                (
                    "render_qualified_name",
                    native_field(adapter, "render_qualified_name")?,
                ),
            ],
        )?),
    )?
    .into_any())
}

/// Run canonical compile, selector, and relation phases without build planning.
#[pyfunction]
#[pyo3(signature = (**request))]
pub(crate) fn compile_static_command_context<'py>(
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
        && !native_field(&options, "sql_test_selection")?
            .getattr("models_selected")?
            .is_truthy()?
    {
        selected_keys = PyFrozenSet::empty(py)?.into_any();
    }
    let compiled: Bound<'py, PyAny> = compile_project_phase(
        py,
        Some(keywords(
            py,
            &[
                ("discovered_inputs", discovered.clone()),
                ("adapter", adapter.clone()),
                ("options", options.clone()),
                (
                    "on_progress",
                    request.optional("on_progress")?.unwrap_or_else(none),
                ),
            ],
        )?),
    )?;
    let project: Bound<'py, PyAny> = native_field(&compiled, "project")?;
    let deferred: Bound<'py, PyAny> =
        deferred_locations((&discovered, &adapter), &options, &project)?;
    let scope: Bound<'py, PyAny> = resolve_static_command_scope(
        &project,
        &new_record_with(
            py,
            RecordId::PlannerSelection,
            &[
                ("select", native_field(&options, "select")?),
                ("exclude", native_field(&options, "exclude")?),
                ("selected_keys", selected_keys),
                (
                    "sql_test_selection",
                    native_field(&options, "sql_test_selection")?,
                ),
            ],
        )?,
        native_field(&options, "auto_load_sources")?.extract()?,
    )?;
    let relations: Bound<'py, PyAny> = resolve_static_relation_context(
        py,
        Some(keywords(
            py,
            &[
                ("project", project.clone()),
                ("adapter", adapter),
                ("scope", scope.clone()),
                (
                    "deferral",
                    new_record_with(
                        py,
                        RecordId::DeferralInputs,
                        &[
                            ("deferred_locations", deferred),
                            (
                                "defer_sources_to",
                                native_field(&options, "defer_sources_to")?,
                            ),
                            (
                                "source_deferral_enabled",
                                native_field(&options, "source_deferral_enabled")?,
                            ),
                        ],
                    )?,
                ),
                (
                    "project_config",
                    native_field(&discovered, "project_config")?,
                ),
                ("local_config", native_field(&discovered, "local_config")?),
                (
                    "relation_keys",
                    request.optional("relation_keys")?.unwrap_or_else(none),
                ),
            ],
        )?),
    )?;
    new_record_with(
        py,
        RecordId::StaticCommandContext,
        &[
            ("project", project),
            ("scope", scope),
            ("relations", relations),
            (
                "connection_config",
                native_field(&compiled, "connection_config")?,
            ),
            (
                "compile_seconds",
                native_field(&compiled, "compile_seconds")?,
            ),
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
