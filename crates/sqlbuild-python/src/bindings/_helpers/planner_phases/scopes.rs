//! Resolve the selected, stale-warning and inspection scopes of one plan.

use crate::bindings::_helpers::analysis::model_reads;
use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::graph::algorithms::transitive_closure_many;
use crate::bindings::_helpers::planner_phases::models::PlannerScopeResolution;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_phases::objects::{replace, tuple};
use crate::bindings::_helpers::planner_scope::scope::build_planner_scope;
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
    let auto_load = policies.getattr("auto_load_sources")?;
    let selected = build_planner_scope(
        py,
        Some(keywords(
            py,
            &[
                ("project", project.clone()),
                ("select", selection.getattr("select")?),
                ("exclude", selection.getattr("exclude")?),
                ("auto_load_sources", auto_load.clone()),
                ("selected_keys", selection.getattr("selected_keys")?),
                (
                    "python_read_source_names",
                    selection.getattr("python_read_source_names")?,
                ),
                (
                    "sql_test_selection",
                    selection.getattr("sql_test_selection")?,
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
            &selected.getattr("selected_keys")?,
            &full.getattr("upstream_deps")?,
            true,
            None,
        )?,
    )?;
    let all_keys = PyDict::new(py);
    for (name, key) in full.getattr("all_keys")?.downcast::<PyDict>()?.iter() {
        if stale_keys.contains(&key)? {
            all_keys.set_item(name, key)?;
        }
    }
    let models = PyDict::new(py);
    for (name, model) in full.getattr("models_by_name")?.downcast::<PyDict>()?.iter() {
        if stale_keys.contains(model_reads::model_key(&model)?)? {
            models.set_item(name, model)?;
        }
    }
    let mut order: Vec<_> = Vec::new();
    for key in full.getattr("execution_order")?.try_iter()? {
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
            ("selected_keys", selected.getattr("selected_keys")?),
            ("execution_order", tuple(py, order)?),
            (
                "user_selected_keys",
                selected.getattr("user_selected_keys")?,
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
