//! The native SQLite Recall store: automatic DDL, idempotent inserts, maintenance and reads.

pub(crate) mod _helpers;
pub mod constants;
pub mod errors;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
