//! Native model configuration: MODEL header metadata, config scans and templates with the Python compiler's rules.

#![forbid(unsafe_code)]

pub mod config_presence;
pub mod declarations;
pub mod errors;
pub mod execution_limits;
pub mod header_metadata;
pub mod model_validation;
pub mod name_patterns;
pub mod path_defaults;
pub mod resource_identities;
pub mod sql_tests;
pub mod sql_values;
pub mod templates;
pub mod types;

#[cfg(test)]
mod tests;
