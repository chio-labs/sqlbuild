//! Project configuration reading: `tomllib`-compatible TOML and PyYAML-compatible YAML.

#![forbid(unsafe_code)]

pub(crate) mod constants;
pub mod errors;
pub mod models;
pub mod project;
pub mod toml;
pub mod yaml;
