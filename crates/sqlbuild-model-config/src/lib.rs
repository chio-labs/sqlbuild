//! Native model configuration: MODEL header metadata, config scans and templates with the Python compiler's rules.

#![forbid(unsafe_code)]

pub mod config_presence;
pub mod errors;
pub mod header_metadata;
pub mod model_validation;
pub mod path_defaults;
pub mod templates;
pub mod types;

#[cfg(test)]
mod tests;
