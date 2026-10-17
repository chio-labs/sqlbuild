//! Resolve the selected, stale-warning and inspection scopes of one plan.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::graph::algorithms::transitive_closure_many;
use crate::bindings::_helpers::planner_phases::models::PlannerScopeResolution;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_phases::objects::{replace, tuple};
use crate::bindings::_helpers::planner_scope::scope::build_planner_scope;
use crate::bindings::_helpers::records::fields::field as native_field;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;
use pyo3::types::{PyDict, PyDictMethods, PyTuple};

#[pyfunction]
#[pyo3(signature = (*, project, selection, policies))]
pub(crate) fn resolve_planner_scopes<'py>(
    project: &Bound<'py, PyAny>,
    selection: &Bound<'py, PyAny>,
    policies: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let py = project.py();
    let auto_load = native_field(policies, "auto_load_sources")?;
    let selected = build_planner_scope(
        py,
        Some(keywords(
            py,
            &[
                ("project", project.clone()),
                ("select", native_field(selection, "select")?),
                ("exclude", native_field(selection, "exclude")?),
                ("auto_load_sources", auto_load.clone()),
                ("selected_keys", native_field(selection, "selected_keys")?),
                (
                    "python_read_source_names",
                    native_field(selection, "python_read_source_names")?,
                ),
                (
                    "sql_test_selection",
                    native_field(selection, "sql_test_selection")?,
                ),
            ],
        )?),
    )?;
    let empty = PyTuple::empty(py).into_any();
    let full = build_planner_scope(
        py,
        Some(keywords(
            py,
            &[
                ("project", project.clone()),
                ("select", empty.clone()),
                ("exclude", empty),
                ("auto_load_sources", auto_load),
            ],
        )?),
    )?;
    let stale_keys = object(
        py,
        transitive_closure_many(
            &native_field(&selected, "selected_keys")?,
            &native_field(&full, "upstream_deps")?,
            true,
            None,
        )?,
    )?;
    let all_keys = PyDict::new(py);
    for (name, key) in native_field(&full, "all_keys")?
        .downcast::<PyDict>()?
        .iter()
    {
        if stale_keys.contains(&key)? {
            all_keys.set_item(name, key)?;
        }
    }
    let models = PyDict::new(py);
    for (name, model) in native_field(&full, "models_by_name")?
        .downcast::<PyDict>()?
        .iter()
    {
        if stale_keys.contains(model_reads::model_key(&model)?)? {
            models.set_item(name, model)?;
        }
    }
    let mut order: Vec<_> = Vec::new();
    for key in native_field(&full, "execution_order")?.try_iter()? {
        let key = key?;
        if stale_keys.contains(&key)? {
            order.push(key);
        }
    }
    let stale_scope = replace(
        &full,
        &[
            ("all_keys", all_keys.into_any()),
            ("models_by_name", models.into_any()),
            ("selected_keys", native_field(&selected, "selected_keys")?),
            ("execution_order", tuple(py, order)?),
            (
                "user_selected_keys",
                native_field(&selected, "user_selected_keys")?,
            ),
        ],
    )?;
    Ok(Bound::new(
        py,
        PlannerScopeResolution {
            selected_scope: selected.clone().unbind(),
            stale_warning_scope: stale_scope.unbind(),
            inspection_scope: selected.unbind(),
        },
    )?
    .into_any())
}
