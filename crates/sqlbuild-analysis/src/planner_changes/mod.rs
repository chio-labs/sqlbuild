//! Planner change detection: replay policy, version-identity metadata, schema findings, reference-rename origins and the per-model change decision.

pub(crate) mod _helpers;
pub mod constants;
pub mod errors;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
