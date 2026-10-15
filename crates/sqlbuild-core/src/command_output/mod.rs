//! Command-output capture: ANSI-free bounded text chunks, buffering and bounded delivery queues.

pub(crate) mod _helpers;
pub mod constants;
pub mod errors;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
