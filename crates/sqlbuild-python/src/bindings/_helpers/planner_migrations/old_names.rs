//! Existing old-name planner models at the native decision boundary.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::KeywordArguments;
use crate::bindings::_helpers::native_host::adapter::AdapterHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::planner_migrations::old_name_objects::relation;
use crate::bindings::_helpers::records::construct::{enum_member, new_record_with};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::ids::RecordId;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{PyDict, PySet, PyTuple};
use pyo3::{IntoPyObject, pyfunction, wrap_pyfunction};
use sqlbuild_analysis::planner_migrations::main::{
    declared_column_aliases as aliases, old_name_claim_message as claim, old_name_schemas,
    old_name_skip_reason,
};

#[pyfunction]
pub(crate) fn declared_column_aliases<'py>(
    py: Python<'py>,
    model: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyTuple>> {
    let schema = native_field(model, "schema_entry")?;
    let mut columns: Vec<(String, Option<String>)> = Vec::new();
    if !schema.is_none() {
        for column in native_field(&schema, "columns")?.try_iter()? {
            let column = column?;
            columns.push((
                native_field(&column, "name")?.extract()?,
                native_field(&column, "migrate_from")?.extract()?,
            ));
        }
    }
    PyTuple::new(py, aliases::declared_column_aliases(&columns))
}

#[pyfunction]
#[pyo3(signature = (*, snapshot, needed))]
pub(crate) fn old_name_schemas_to_read<'py>(
    py: Python<'py>,
    snapshot: &Bound<'py, PyAny>,
    needed: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PySet>> {
    let listed: Option<std::collections::BTreeSet<String>> =
        native_field(snapshot, "listed_state_schemas")?.extract()?;
    PySet::new(
        py,
        old_name_schemas::old_name_schemas(
            &needed.extract()?,
            &native_field(snapshot, "old_name_view_state_schemas")?.extract()?,
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
    let old = native_field(view, "old")?;
    let qualified: Option<String> = native_field(&old, "qualified_name")?.extract()?;
    let name: String = qualified
        .filter(|name| !name.is_empty())
        .unwrap_or(native_field(&old, "name")?.extract()?);
    let expires = native_field(view, "expires_at")?;
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
            &native_field(view, "destination_model")?.extract::<String>()?,
        ),
        (date.as_deref(), expired),
    ))
}

#[pyfunction]
#[pyo3(signature = (**options))]
pub(crate) fn old_name_claim_errors<'py>(
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
        let name = model_reads::name_object(&model)?;
        let existing = arguments
            .value("snapshot")?
            .getattr("existing_relations")?
            .call_method1("get", (&name,))?;
        if existing.is_none() {
            continue;
        }
        let kind = host::entry(py, AdapterHost::NormalizeRelationType)?
            .call1((native_field(&existing, "relation_type")?,))?;
        if !kind.eq("view")? {
            continue;
        }
        let destination = relation(&model_reads::destination(&model)?)?;
        for view in arguments.value("views")?.try_iter()? {
            let view = view?;
            if native_field(&view, "destination_model")?.eq(&name)?
                || !relation(&native_field(&view, "old")?)?
                    .call_method1("matches", (&destination,))?
                    .is_truthy()?
            {
                continue;
            }
            let message =
                claim_message(&name.extract::<String>()?, &view, &arguments.value("now")?)?;
            errors.push(new_record_with(
                py,
                RecordId::PlanWarning,
                &[
                    ("model_name", name.clone()),
                    (
                        "severity",
                        enum_member(py, RecordId::WarningSeverity, "ERROR")?,
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
pub(crate) fn old_name_view_skip_reason<'py>(
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
        if relation(&model_reads::destination(&model)?)?
            .call_method1("matches", (&old,))?
            .is_truthy()?
        {
            reuser = Some(model_reads::name_object(&model)?.extract()?);
            break;
        }
    }
    let mut compatibility_view = false;
    if reuser.is_none() {
        for view in arguments.value("views")?.try_iter()? {
            if relation(&native_field(&view?, "old")?)?
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
