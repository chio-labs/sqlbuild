//! Enforceable SQL quality Rules with project-wide limits and ranking determinism proofs.

pub(crate) mod constants;
#[path = "_helpers/cte_columns.rs"]
mod cte_columns;
#[path = "_helpers/keys.rs"]
mod keys;
#[path = "_helpers/literals.rs"]
mod literals;
pub(crate) mod main;
pub(crate) mod models;
#[path = "_helpers/ranking.rs"]
mod ranking;
#[path = "_helpers/removal_safety.rs"]
mod removal_safety;
#[path = "_helpers/syntax.rs"]
mod syntax;
pub(crate) mod types;

#[cfg(test)]
mod tests;
