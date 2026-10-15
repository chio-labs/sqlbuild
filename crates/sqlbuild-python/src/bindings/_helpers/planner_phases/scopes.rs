//! Resolve the selected, stale-warning and inspection scopes of one plan.

use crate::bindings::_helpers::planner_phases::objects::{native, replace, tuple};
use pyo3::IntoPyObject;
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
    let selected = native(
        py,
        "build_planner_scope",
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
    )?;
    let empty = PyTuple::empty(py).into_any();
    let full = native(
        py,
        "build_planner_scope",
        &[
            ("project", project.clone()),
            ("select", empty.clone()),
            ("exclude", empty),
            ("auto_load_sources", auto_load),
        ],
    )?;
    let stale_keys = native(
        py,
        "transitive_closure_many",
        &[
            ("starts", selected.getattr("selected_keys")?),
            ("edges", full.getattr("upstream_deps")?),
            (
                "include_starts",
                true.into_pyobject(py)?.to_owned().into_any(),
            ),
        ],
    )?;
    let all_keys = PyDict::new(py);
    for (name, key) in full.getattr("all_keys")?.downcast::<PyDict>()?.iter() {
        if stale_keys.contains(&key)? {
            all_keys.set_item(name, key)?;
        }
    }
    let models = PyDict::new(py);
    for (name, model) in full.getattr("models_by_name")?.downcast::<PyDict>()?.iter() {
        if stale_keys.contains(model.getattr("key")?)? {
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
    native(
        py,
        "PlannerScopeResolution",
        &[
            ("selected_scope", selected.clone()),
            ("stale_warning_scope", stale_scope),
            ("inspection_scope", selected),
        ],
    )
}
