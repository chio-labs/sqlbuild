//! The append-only fingerprint table: its DDL, latest-row reads, batched inserts and row decoding.

pub(crate) mod _helpers;
pub mod constants;
pub mod errors;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
