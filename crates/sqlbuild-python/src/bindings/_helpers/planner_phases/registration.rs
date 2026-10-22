//! Register the native execution-planning phases.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::wrap_pyfunction;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<super::models::PlannerRuntime>()?;
    module.add_class::<super::models::PlannerWarehouseState>()?;
    module.add_class::<super::models::PlannerScopeResolution>()?;
    module.add_class::<super::models::PlannerIdentityContext>()?;
    module.add_function(wrap_pyfunction!(
        super::scopes::resolve_planner_scopes,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::identities::planner_identity_work_info,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::identities::detect_stale_warning_changes_of,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::full_refresh::describe_full_rebuild_cause,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::full_refresh::check_full_rebuild_allowed,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::retention::table_type_copy_name,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::retention::plan_table_types,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(super::retention::plan_retention, module)?)?;
    Ok(())
}
