//! Register the native `sqb` argument parsing, command dispatch and command handlers.

use pyo3::prelude::{Bound, PyModule, PyResult};

use crate::bindings::_helpers::cli::{argv, entry, progress, progress_reporters, progress_text};
use crate::bindings::_helpers::{
    audit_command, check, clone, command_runtime, contract_command, cost_report, dbt_interop,
    debug_command, diff_report, freshness, init_command, janitor, load, presentation_text,
    query_command, result_output, scenario_command, seed_command, sql_test_command,
    workspace_commands,
};

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    argv::register(module)?;
    entry::register(module)?;
    progress::register(module)?;
    progress_reporters::register(module)?;
    progress_text::register(module)?;
    janitor::registration::register(module)?;
    freshness::registration::register(module)?;
    clone::registration::register(module)?;
    load::registration::register(module)?;
    result_output::registration::register(module)?;
    cost_report::registration::register(module)?;
    debug_command::registration::register(module)?;
    dbt_interop::registration::register(module)?;
    diff_report::registration::register(module)?;
    command_runtime::registration::register(module)?;
    presentation_text::registration::register(module)?;
    workspace_commands::registration::register(module)?;
    check::registration::register(module)?;
    sql_test_command::registration::register(module)?;
    seed_command::registration::register(module)?;
    audit_command::registration::register(module)?;
    query_command::registration::register(module)?;
    scenario_command::registration::register(module)?;
    contract_command::registration::register(module)?;
    init_command::registration::register(module)?;
    Ok(())
}
