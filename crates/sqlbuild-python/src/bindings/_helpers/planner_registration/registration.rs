//! Registers every planner binding group.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::{
    planner_changes, planner_entries, planner_identity, planner_migrations, planner_phases,
    planner_resolution, planner_scenario, planner_scope, planner_selection, planner_strategy,
    planner_warehouse, relation_naming,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    planner_changes::registration::register(module)?;
    planner_migrations::registration::register(module)?;
    planner_phases::registration::register(module)?;
    planner_warehouse::registration::register(module)?;
    planner_identity::registration::register(module)?;
    planner_selection::registration::register(module)?;
    planner_scope::registration::register(module)?;
    planner_scenario::registration::register(module)?;
    planner_strategy::registration::register(module)?;
    planner_resolution::registration::register(module)?;
    planner_entries::registration::register(module)?;
    relation_naming::registration::register(module)?;
    Ok(())
}
