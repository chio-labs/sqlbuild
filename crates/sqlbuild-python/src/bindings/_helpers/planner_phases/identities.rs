//! Expected version identities and stale-warning change detection.

use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::planner_phases::contexts::class_field;
use crate::bindings::_helpers::planner_phases::models::PlannerIdentityContext;
use crate::bindings::_helpers::planner_phases::models::PlannerScopeResolution;
use crate::bindings::_helpers::planner_phases::objects::{frozenset, native, replace};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::{NativeAttr, RecordId};
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
        NativeAttr::BuildDirectModelVersionIdentities,
        &[
            ("functions", native_field(project, "functions")?),
            ("seeds", native_field(project, "seeds")?),
            ("scope", scope),
            ("hook_functions", native_field(project, "hook_functions")?),
            ("dialect", native_field(project, "sql_analysis_dialect")?),
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
    let identities = version_identities(
        project,
        class_field(scopes, |s: &PlannerScopeResolution| &s.inspection_scope)?,
    )?;
    let stale = if include_stale_warning_identities {
        version_identities(
            project,
            class_field(scopes, |s: &PlannerScopeResolution| &s.stale_warning_scope)?,
        )?
    } else {
        identities.clone()
    };
    Ok(Bound::new(
        project.py(),
        PlannerIdentityContext {
            version_identities: identities.unbind(),
            stale_warning_identities: stale.unbind(),
        },
    )?
    .into_any())
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
    let execution = class_field(identities, |i: &PlannerIdentityContext| {
        &i.version_identities
    })?;
    let stale = class_field(identities, |i: &PlannerIdentityContext| {
        &i.stale_warning_identities
    })?;
    for name in native_field(execution_changes, "models")?.try_iter()? {
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

#[pyfunction(name = "detect_stale_warning_changes")]
#[pyo3(signature = (**options))]
pub(crate) fn detect_stale_warning_changes_of<'py>(
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
    detect_stale_warning_changes(
        (&args.value("project")?, &args.value("scopes")?),
        &args.value("snapshot")?,
        (
            &args.value("identities")?,
            &args.value("execution_changes")?,
        ),
    )
}

/// Changes of stale-warning models whose identities differ from the execution identities.
pub(crate) fn detect_stale_warning_changes<'py>(
    (project, scopes): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
    snapshot: &Bound<'py, PyAny>,
    (identities, execution_changes): (&Bound<'py, PyAny>, &Bound<'py, PyAny>),
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let reusable = reusable_model_names(
        identities,
        execution_changes,
        project
            .getattr("settings")?
            .getattr("query_change_tracking")?
            .is_truthy()?,
    )?;
    let stale_scope = class_field(scopes, |s: &PlannerScopeResolution| &s.stale_warning_scope)?;
    let mut remaining: Vec<_> = Vec::new();
    for key in stale_scope
        .getattr("all_keys")?
        .call_method0("values")?
        .try_iter()?
    {
        let key = key?;
        if native_field(&key, "resource_type")?.eq("model")?
            && !reusable.contains(&native_field(&key, "name")?.extract::<String>()?)
        {
            remaining.push(key);
        }
    }
    let stale_identities = class_field(identities, |i: &PlannerIdentityContext| {
        &i.stale_warning_identities
    })?;
    let remaining_changes = native(
        py,
        NativeAttr::DetectModelChangesInScope,
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
                native_field(&stale_identities, "model_version_hashes")?,
            ),
            (
                "expected_metadata_jsons",
                native_field(&stale_identities, "model_metadata_jsons")?,
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
    native(
        py,
        RecordId::PlannerChangeResults,
        &[
            ("models", models.into_any()),
            ("functions", PyDict::new(py).into_any()),
        ],
    )
}
