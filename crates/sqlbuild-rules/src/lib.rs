//! Built-in rules, SQL lint, quality checks and formatting, with their configuration.

#![forbid(unsafe_code)]

pub mod configuration;
pub mod constants;
pub mod engine;
pub mod errors;
pub mod models;
pub mod rules;
pub mod scope_metadata;
pub mod sql_lint;
pub mod sql_quality;
pub mod types;
