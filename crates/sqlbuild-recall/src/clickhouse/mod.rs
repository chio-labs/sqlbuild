//! The ClickHouse Recall store's native parts: row encoding, stored-row lookups, insert planning, error kinds and retention conflicts. The connection is the ClickHouse adapter's, driven by the host.

pub(crate) mod _helpers;
pub mod constants;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
