//! Existing old-name planner models at the native decision boundary.

use crate::bindings::_helpers::compile_driver::python_calls::{
    KeywordArguments, call_with, imported,
};
use crate::bindings::_helpers::planner_migrations::old_name_objects::relation;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PySet, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_migrations::main::{
    declared_column_aliases as aliases, old_name_claim_message as claim, old_name_schemas,
    old_name_skip_reason,
};

#[pyfunction]
fn declared_column_aliases<'py>(
    py: Python<'py>,
    model: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let schema = model.getattr("schema_entry")?;
    let mut columns: Vec<(String, Option<String>)> = Vec::new();
    if !schema.is_none() {
        for column in schema.getattr("columns")?.try_iter()? {
            let column = column?;
            columns.push((
                column.getattr("name")?.extract()?,
                column.getattr("migrate_from")?.extract()?,
            ));
        }
    }
    PyTuple::new(py, aliases::declared_column_aliases(&columns))
}

#[pyfunction]
#[pyo3(signature = (*, snapshot, needed))]
fn old_name_schemas_to_read<'py>(
    py: Python<'py>,
    snapshot: &Bound<'py, PyAny>,
    needed: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PySet>> {
    let listed: Option<std::collections::BTreeSet<String>> =
        snapshot.getattr("listed_state_schemas")?.extract()?;
    PySet::new(
        py,
        old_name_schemas::old_name_schemas(
            &needed.extract()?,
            &snapshot.getattr("old_name_view_state_schemas")?.extract()?,
            listed.as_ref(),
        ),
    )
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn old_name_claim_message<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<String> {
    let arguments = KeywordArguments::read(
        py,
        "old_name_claim_message",
        options,
        (&["model_name", "view", "now"], &[]),
    )?;
    claim_message(
        &arguments.value("model_name")?.extract::<String>()?,
        &arguments.value("view")?,
        &arguments.value("now")?,
    )
}

fn claim_message(model: &str, view: &Bound<'_, PyAny>, now: &Bound<'_, PyAny>) -> PyResult<String> {
    let old = view.getattr("old")?;
    let qualified: Option<String> = old.getattr("qualified_name")?.extract()?;
    let name: String = qualified
        .filter(|name| !name.is_empty())
        .unwrap_or(old.getattr("name")?.extract()?);
    let expires = view.getattr("expires_at")?;
    let date: Option<String> = if expires.is_none() {
        None
    } else {
        Some(expires.call_method1("strftime", ("%Y-%m-%d",))?.extract()?)
    };
    let expired = !expires.is_none() && expires.le(now)?;
    Ok(claim::old_name_claim_message(
        model,
        (
            &name,
            &view.getattr("destination_model")?.extract::<String>()?,
        ),
        (date.as_deref(), expired),
    ))
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn old_name_claim_errors<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Bound<'py, PyTuple>> {
    let arguments = KeywordArguments::read(
        py,
        "old_name_claim_errors",
        options,
        (&["selected", "snapshot", "views", "now"], &[]),
    )?;
    let mut errors: Vec<Bound<'py, PyAny>> = Vec::new();
    for model in arguments.value("selected")?.try_iter()? {
        let model = model?;
        let name = model.getattr("name")?;
        let existing = arguments
            .value("snapshot")?
            .getattr("existing_relations")?
            .call_method1("get", (&name,))?;
        if existing.is_none() {
            continue;
        }
        let kind = imported(
            py,
            "sqlbuild.adapter.type_system.main.normalize_relation_type",
            "normalize_relation_type",
        )?
        .call1((existing.getattr("relation_type")?,))?;
        if !kind.eq("view")? {
            continue;
        }
        let destination = relation(&model.getattr("destination")?)?;
        for view in arguments.value("views")?.try_iter()? {
            let view = view?;
            if view.getattr("destination_model")?.eq(&name)?
                || !relation(&view.getattr("old")?)?
                    .call_method1("matches", (&destination,))?
                    .is_truthy()?
            {
                continue;
            }
            let message =
                claim_message(&name.extract::<String>()?, &view, &arguments.value("now")?)?;
            errors.push(call_with(
                &imported(py, "sqlbuild._native", "PlanWarning")?,
                &[
                    ("model_name", name.clone()),
                    (
                        "severity",
                        imported(py, "sqlbuild.compiler.planner.types", "WarningSeverity")?
                            .getattr("ERROR")?,
                    ),
                    ("message", message.into_pyobject(py)?.into_any()),
                    ("code", "M114".into_pyobject(py)?.into_any()),
                ],
            )?);
            break;
        }
    }
    PyTuple::new(py, errors)
}

#[pyfunction]
#[pyo3(signature = (**options))]
fn old_name_view_skip_reason<'py>(
    py: Python<'py>,
    options: Option<Bound<'py, PyDict>>,
) -> PyResult<Option<String>> {
    let arguments = KeywordArguments::read(
        py,
        "old_name_view_skip_reason",
        options,
        (
            &["origin", "origin_tracked", "retention", "models", "views"],
            &[],
        ),
    )?;
    let retained = !arguments.value("retention")?.is_none();
    if !retained {
        return Ok(old_name_skip_reason::old_name_skip_reason(
            false, None, false, None,
        ));
    }
    let old = relation(&arguments.value("origin")?)?;
    let mut reuser: Option<String> = None;
    for model in arguments.value("models")?.try_iter()? {
        let model = model?;
        if relation(&model.getattr("destination")?)?
            .call_method1("matches", (&old,))?
            .is_truthy()?
        {
            reuser = Some(model.getattr("name")?.extract()?);
            break;
        }
    }
    let mut compatibility_view = false;
    if reuser.is_none() {
        for view in arguments.value("views")?.try_iter()? {
            if relation(&view?.getattr("old")?)?
                .call_method1("matches", (&old,))?
                .is_truthy()?
            {
                compatibility_view = true;
                break;
            }
        }
    }
    Ok(old_name_skip_reason::old_name_skip_reason(
        true,
        reuser.as_deref(),
        compatibility_view,
        arguments.value("origin_tracked")?.extract()?,
    ))
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(declared_column_aliases, module)?)?;
    module.add_function(wrap_pyfunction!(old_name_schemas_to_read, module)?)?;
    module.add_function(wrap_pyfunction!(old_name_claim_message, module)?)?;
    module.add_function(wrap_pyfunction!(old_name_claim_errors, module)?)?;
    module.add_function(wrap_pyfunction!(old_name_view_skip_reason, module)?)
}
