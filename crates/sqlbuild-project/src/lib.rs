//! The compiled project as plain Rust: each resource's records, with host values held as opaque handles.

#![forbid(unsafe_code)]

mod _helpers;

pub mod models;
pub mod types;

#[cfg(test)]
mod tests;
