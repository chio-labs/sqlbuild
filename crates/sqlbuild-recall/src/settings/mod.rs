//! Effective Recall settings: `[recall]`, `targets.<name>.recall` and the store connection.

pub(crate) mod _helpers;
pub mod constants;
pub mod errors;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
