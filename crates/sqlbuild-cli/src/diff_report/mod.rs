//! The `sqb diff` summary and JSON documents rendered from plain diff facts.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod errors;
pub mod main;
pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
