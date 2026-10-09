//! Semantic completion: type recovery, metadata checks, diagnostic recovery and explanations.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
