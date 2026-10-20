//! The contract of the permanent Python edges: host entries, timings, diagnostics and results.

#![forbid(unsafe_code)]

pub mod compile_context;
pub mod entries;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
