//! Shared foundations of the SQLBuild native workspace: identities, diagnostics, text and typed values.

#![forbid(unsafe_code)]

pub mod constants;
pub mod models;
pub mod panics;
pub mod text;

#[cfg(test)]
mod tests;
