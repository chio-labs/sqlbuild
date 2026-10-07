//! Native model configuration: MODEL header metadata, config scans and templates with the Python compiler's rules.

#![forbid(unsafe_code)]

pub mod config_presence;
pub mod header_metadata;
pub mod templates;
pub mod types;

#[cfg(test)]
mod tests;
