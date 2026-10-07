//! Lexical SQL text: scanning, model headers, static variable substitution and references.

#![forbid(unsafe_code)]

pub mod compiler;
mod constants;
pub mod sql_references;
pub mod sql_scan;
