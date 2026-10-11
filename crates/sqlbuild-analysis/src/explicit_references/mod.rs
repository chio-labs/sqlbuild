//! Compile's explicit-reference checks: audit gates, hook reads and Python-SQL relation names.

pub(crate) mod _helpers;
mod constants;
pub mod errors;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
