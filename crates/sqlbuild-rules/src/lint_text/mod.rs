//! Authored-SQL text transforms for lint and format: interpolation sentinels and suppressions.

pub(crate) mod _helpers;
pub mod constants;
pub mod errors;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
