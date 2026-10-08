//! Fast column lineage facts for compiled models.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub(crate) mod errors;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
