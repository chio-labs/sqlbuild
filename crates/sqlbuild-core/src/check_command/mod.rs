//! `sqb check`: check selection errors, grouped result rows, JSON payload and the exit code.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod errors;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
