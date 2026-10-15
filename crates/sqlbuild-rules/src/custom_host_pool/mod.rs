//! Custom-rule host fan-out: invocation order, host partitions, CPU capacity and merged results.

pub(crate) mod _helpers;
pub mod constants;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
