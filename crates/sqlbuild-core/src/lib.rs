//! Shared foundations of the SQLBuild native workspace: identities, diagnostics, text and JSON.

#![forbid(unsafe_code)]

pub mod cli_text;
pub mod clone_text;
pub mod constants;
pub mod cost_report;
pub mod debug_report;
pub mod freshness_text;
pub mod integration_results;
pub mod janitor_text;
pub mod json;
pub mod models;
pub mod panics;
pub mod posix_path;
pub mod progress;
pub mod terminal_events;
pub mod text;

#[cfg(test)]
mod tests;
