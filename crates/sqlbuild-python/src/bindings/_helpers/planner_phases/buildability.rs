//! Selected-scope buildability validation before change planning.

use crate::bindings::_helpers::compile_driver::python_calls::keywords;
use crate::bindings::_helpers::planner_identity::graph::build_execution_edge_origins;
use crate::bindings::_helpers::planner_identity::graph::check_buildability;
use crate::bindings::_helpers::planner_identity::graph::missing_upstream_message;
use crate::bindings::_helpers::planner_phases::constants::MISSING_UPSTREAM_CODE;
use crate::bindings::_helpers::planner_phases::contexts::class_field;
use crate::bindings::_helpers::planner_phases::models::PlannerScopeResolution;
use crate::bindings::_helpers::planner_phases::objects::object;
use crate::bindings::_helpers::planner_phases::objects::{frozenset, planner_error};
use crate::bindings::_helpers::planner_phases::runtime::runtime_field;
use crate::bindings::_helpers::planner_phases::runtime::warehouse_field;
use crate::bindings::_helpers::planner_warehouse::source_tables::check_selected_source_tables_exist;
use crate::bindings::_helpers::records::fields::field as native_field;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::pyfunction;

#[pyfunction]
#[pyo3(signature = (*, runtime, scopes, warehouse, deferral))]
pub(crate) fn check_selected_scope_buildability<'py>(
    runtime: &Bound<'py, PyAny>,
    scopes: &Bound<'py, PyAny>,
    warehouse: &Bound<'py, PyAny>,
    deferral: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let py = runtime.py();
    let project = runtime_field(runtime, |runtime| &runtime.project)?;
    let selected_scope = class_field(scopes, |s: &PlannerScopeResolution| &s.selected_scope)?;
    let mut external_seeds: Vec<_> = Vec::new();
    for seed in native_field(&project, "seeds")?.try_iter()? {
        let seed = seed?;
        if native_field(&seed, "external")?.is_truthy()? {
            external_seeds.push(native_field(&seed, "key")?);
        }
    }
    let missing = object(
        py,
        check_buildability(
            py,
            Some(keywords(
                py,
                &[
                    (
                        "selected_keys",
                        native_field(&selected_scope, "selected_keys")?,
                    ),
                    (
                        "upstream_deps",
                        native_field(&selected_scope, "upstream_deps")?,
                    ),
                    (
                        "snapshot",
                        warehouse_field(warehouse, |warehouse| &warehouse.snapshot)?,
                    ),
                    (
                        "deferred_relations",
                        native_field(deferral, "deferred_relations")?,
                    ),
                    ("satisfied_keys", frozenset(py, &external_seeds)?),
                ],
            )?),
        )?,
    )?;
    if missing.is_truthy()? {
        let message: String = object(
            py,
            missing_upstream_message(
                &missing,
                &object(py, build_execution_edge_origins(&project)?)?,
            )?,
        )?
        .extract()?;
        return Err(planner_error(
            py,
            &message,
            (Some(MISSING_UPSTREAM_CODE), None),
        ));
    }
    check_selected_source_tables_exist(
        &project,
        (
            &runtime_field(runtime, |runtime| &runtime.adapter)?,
            &runtime_field(runtime, |runtime| &runtime.connection)?,
        ),
        &selected_scope,
        &warehouse_field(warehouse, |warehouse| &warehouse.inspection_relations)?,
    )
}
