//! Model and column migration decisions: what each decision does and when it blocks a build.

pub(crate) mod constants;
pub mod main;
pub mod models;

#[cfg(test)]
mod tests;
