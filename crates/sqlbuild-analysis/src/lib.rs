//! SQL analysis over polyglot: query facts, binding catalog, semantic validation and SQL tests.

#![forbid(unsafe_code)]

pub mod column_references;
pub mod compiler;
mod constants;
pub mod query_analysis;
pub mod semantic_usage;
pub mod semantic_validation;
pub mod sql_tokens;
