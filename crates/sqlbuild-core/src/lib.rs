//! Shared foundations of the SQLBuild native workspace: identities, diagnostics, text and JSON.

#![forbid(unsafe_code)]

pub mod constants;
pub mod json;
pub mod models;
pub mod panics;
pub mod text;

#[cfg(test)]
mod tests;
