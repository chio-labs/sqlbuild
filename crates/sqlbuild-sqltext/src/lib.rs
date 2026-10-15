//! Lexical SQL text: scanning, model headers, static variable substitution and references.

#![forbid(unsafe_code)]

pub mod code_scanner;
pub mod compiler;
mod constants;
pub mod ddl_effects;
pub mod resolution;
pub mod sql_references;
pub mod sql_scan;
