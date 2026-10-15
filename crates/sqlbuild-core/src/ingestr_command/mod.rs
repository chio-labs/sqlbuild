//! The `ingestr ingest` command line for one declarative ingestr source and its warehouse.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod errors;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
