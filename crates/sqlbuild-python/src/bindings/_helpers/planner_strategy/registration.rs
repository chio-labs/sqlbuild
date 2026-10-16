//! Register the planner strategy.

use pyo3::prelude::{Bound, PyModule, PyResult};
use pyo3::{prelude::PyModuleMethods, wrap_pyfunction};

use crate::bindings::_helpers::planner_strategy::{
    audits, cursor_types, fixture_completion, fixture_sql, lineage, microbatches, strategy,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(
        super::audit_entries::plan_audit_of,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::audit_entries::audit_is_selected,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::audit_entries::build_selected_audit_entries,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::cursor_inputs::cursor_input_columns_of,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::cursor_inputs::cursor_input_relations_of,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::cursor_inputs::runtime_cursor_producer_names,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::model_entries::resolve_microbatch_lookback,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::model_entries::extract_seed_columns,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::microbatch_limits::apply_microbatch_limit,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(
        super::microbatch_limits::apply_configured_microbatch_limits,
        module
    )?)?;
    audits::register(module)?;
    cursor_types::register(module)?;
    fixture_completion::register(module)?;
    fixture_sql::register(module)?;
    super::fixture_context::register(module)?;
    super::fixture_reads::register(module)?;
    lineage::register(module)?;
    microbatches::register(module)?;
    strategy::register(module)
}
