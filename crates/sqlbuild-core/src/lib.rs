//! Shared foundations of the SQLBuild native workspace: identities, diagnostics, text and JSON.

#![forbid(unsafe_code)]

pub mod audit_command;
pub mod build_command;
pub mod build_progress;
pub mod check_command;
pub mod cli_text;
pub mod clone_text;
pub mod constants;
pub mod contract_command;
pub mod cost_command;
pub mod cost_report;
pub mod dbt_cli;
pub mod dbt_command;
pub mod dbt_events;
pub mod dbt_graph;
pub mod dbt_plan;
pub mod debug_report;
pub mod format_command;
pub mod freshness_text;
pub mod init_command;
pub mod integration_results;
pub mod janitor_text;
pub mod json;
pub mod load_command;
pub mod models;
pub mod nested_progress;
pub mod panics;
pub mod plan_display;
pub mod posix_path;
pub mod progress;
pub mod query_command;
pub mod redaction;
pub mod scenario_command;
pub mod seed_command;
pub mod terminal_events;
pub mod test_command;
pub mod text;

#[cfg(test)]
mod tests;
