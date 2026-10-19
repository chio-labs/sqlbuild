//! Interpreter discovery, its cache, and starting CPython in this process.

pub(crate) mod _helpers;
pub mod constants;
pub mod main;
pub mod models;

#[cfg(all(test, unix))]
mod tests;
