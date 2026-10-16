//! Interpreter and site-path stamps that must be unchanged before Python startup is skipped.

pub(crate) mod _helpers;
pub(crate) mod constants;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
