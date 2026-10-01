#![forbid(unsafe_code)]

pub mod bindings;
mod column_references;
mod compiler;
mod configuration;
mod constants;
mod engine;
mod models;
mod query_analysis;
mod rules;
mod scope_metadata;
mod semantic_usage;
mod semantic_validation;
mod sql_lint;
mod sql_quality;
mod sql_scan;
mod sql_tokens;
