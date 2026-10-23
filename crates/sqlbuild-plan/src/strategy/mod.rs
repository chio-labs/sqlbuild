//! Planner strategy: plan actions and reasons, schema actions, model warnings, audit attachment and run scope, cursor type checks, watermark lineage and microbatch counting and capping.

pub(crate) mod _helpers;
pub mod constants;
pub mod errors;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
