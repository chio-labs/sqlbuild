//! Shared foundations of the SQLBuild native workspace: identities, diagnostics, text and JSON.

#![forbid(unsafe_code)]

pub mod audit_command;
pub mod check_command;
pub mod cli_text;
pub mod clone_text;
pub mod constants;
pub mod cost_report;
pub mod debug_report;
pub mod freshness_text;
pub mod integration_results;
pub mod janitor_text;
pub mod json;
pub mod load_command;
pub mod models;
pub mod panics;
pub mod posix_path;
pub mod progress;
pub mod query_command;
pub mod redaction;
pub mod seed_command;
pub mod terminal_events;
pub mod test_command;
pub mod text;

#[cfg(test)]
mod tests;
