//! SQL analysis over polyglot: query facts, binding catalog, semantic validation and SQL tests.

#![forbid(unsafe_code)]

pub mod assembly;
pub mod column_references;
pub mod compiled_project;
pub mod compiler;
mod constants;
pub mod contracts;
pub mod graph;
pub mod lineage;
pub mod query_analysis;
pub mod semantic_checks;
pub mod semantic_usage;
pub mod semantic_validation;
pub mod sql_tokens;
pub mod type_system;
