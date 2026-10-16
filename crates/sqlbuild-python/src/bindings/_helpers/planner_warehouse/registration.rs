//! Register native warehouse inspection for planning.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult};
use pyo3::wrap_pyfunction;

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<super::fingerprint_cache::MigrationFingerprintCache>()?;
    module.add_function(wrap_pyfunction!(
        super::fingerprint_cache::migration_fingerprint_work_info,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::snapshot::gather_warehouse_snapshot,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::snapshot::gather_redirected_cursor_snapshots,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::watermarks::watermark_type_is_compatible,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::source_columns::gather_source_columns,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::snapshot::planner_metadata_name_filter,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::semantic_sources::list_source_candidates,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::source_columns::gather_source_inspection,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::semantic_sources::semantic_source_columns,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::source_tables::check_selected_source_tables_exist_binding,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::source_deferral::build_source_read_map,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::source_deferral::with_declared_source_reads,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::source_freshness::source_freshness_unknown_warnings,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::source_freshness::build_planner_source_freshness_result_of,
        module
    )?)
}
