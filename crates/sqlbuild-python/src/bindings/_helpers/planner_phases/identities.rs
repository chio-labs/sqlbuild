//! Expected version identities and stale-warning change detection.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::planner_phases::objects::{
    frozenset, native, planner_model, replace,
};
use pyo3::IntoPyObject;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::PyDict as KeywordDict;
use pyo3::types::{PyDict, PyDictMethods};
use std::collections::HashSet;

fn version_identities<'py>(
    project: &Bound<'py, PyAny>,
    scope: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    native(
        project.py(),
        "build_direct_model_version_identities",
        &[
            ("functions", project.getattr("functions")?),
            ("seeds", project.getattr("seeds")?),
            ("scope", scope),
            ("hook_functions", project.getattr("hook_functions")?),
            ("dialect", project.getattr("sql_analysis_dialect")?),
        ],
    )
}

#[pyfunction]
#[pyo3(signature = (*, project, scopes, include_stale_warning_identities=true))]
pub(crate) fn build_planner_identity_context<'py>(
    project: &Bound<'py, PyAny>,
    scopes: &Bound<'py, PyAny>,
    include_stale_warning_identities: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let identities = version_identities(project, scopes.getattr("inspection_scope")?)?;
    let stale = if include_stale_warning_identities {
        version_identities(project, scopes.getattr("stale_warning_scope")?)?
    } else {
        identities.clone()
    };
    planner_model(
        project.py(),
        "PlannerIdentityContext",
        &[
            ("version_identities", identities),
            ("stale_warning_identities", stale),
        ],
    )
}

fn reusable_model_names(
    identities: &Bound<'_, PyAny>,
    execution_changes: &Bound<'_, PyAny>,
    query_change_tracking: bool,
) -> PyResult<HashSet<String>> {
    let mut names: HashSet<_> = HashSet::new();
    if !query_change_tracking {
        return Ok(names);
    }
    let execution = identities.getattr("version_identities")?;
    let stale = identities.getattr("stale_warning_identities")?;
    for name in execution_changes.getattr("models")?.try_iter()? {
        let name = name?;
        let same = |field: &str| -> PyResult<bool> {
            execution
                .getattr(field)?
                .call_method1("get", (&name,))?
                .eq(stale.getattr(field)?.call_method1("get", (&name,))?)
        };
        if same("model_version_hashes")? && same("model_metadata_jsons")? {
            names.insert(name.extract()?);
        }
    }
    Ok(names)
}

#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn detect_stale_warning_changes<'py>(
    py: pyo3::Python<'py>,
    options: Option<Bound<'py, KeywordDict>>,
) -> PyResult<Bound<'py, PyAny>> {
    let args = KeywordArguments::read(
        py,
        "detect_stale_warning_changes",
        options,
        (
            &[
                "project",
                "scopes",
                "snapshot",
                "identities",
                "execution_changes",
            ],
            &[],
        ),
    )?;
    let project = &args.value("project")?;
    let scopes = &args.value("scopes")?;
    let snapshot = &args.value("snapshot")?;
    let identities = &args.value("identities")?;
    let execution_changes = &args.value("execution_changes")?;

    let py = project.py();
    let reusable = reusable_model_names(
        identities,
        execution_changes,
        project
            .getattr("settings")?
            .getattr("query_change_tracking")?
            .is_truthy()?,
    )?;
    let stale_scope = scopes.getattr("stale_warning_scope")?;
    let mut remaining: Vec<_> = Vec::new();
    for key in stale_scope
        .getattr("all_keys")?
        .call_method0("values")?
        .try_iter()?
    {
        let key = key?;
        if key.getattr("resource_type")?.eq("model")?
            && !reusable.contains(&key.getattr("name")?.extract::<String>()?)
        {
            remaining.push(key);
        }
    }
    let stale_identities = identities.getattr("stale_warning_identities")?;
    let remaining_changes = native(
        py,
        "detect_model_changes_in_scope",
        &[
            ("project", project.clone()),
            (
                "scope",
                replace(
                    &stale_scope,
                    &[("selected_keys", frozenset(py, &remaining)?)],
                )?,
            ),
            ("snapshot", snapshot.clone()),
            (
                "query_change_tracking",
                true.into_pyobject(py)?.to_owned().into_any(),
            ),
            (
                "expected_version_hashes",
                stale_identities.getattr("model_version_hashes")?,
            ),
            (
                "expected_metadata_jsons",
                stale_identities.getattr("model_metadata_jsons")?,
            ),
        ],
    )?;
    let models = PyDict::new(py);
    for (name, change) in execution_changes
        .getattr("models")?
        .downcast::<PyDict>()?
        .iter()
    {
        if reusable.contains(&name.extract::<String>()?) {
            models.set_item(name, change)?;
        }
    }
    for (name, change) in remaining_changes.downcast::<PyDict>()?.iter() {
        models.set_item(name, change)?;
    }
    planner_model(
        py,
        "PlannerChangeResults",
        &[
            ("models", models.into_any()),
            ("functions", PyDict::new(py).into_any()),
        ],
    )
}
