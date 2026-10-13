//! The custom-rule result cache: rule and subject identities, read-set lookup and the cache file.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod errors;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
