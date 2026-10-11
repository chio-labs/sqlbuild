//! Parse one MODEL header's `dynamic_columns`, with the errors Python raises.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::dynamic::{DynamicSource, dynamic_families};
use crate::header_metadata::models::DynamicFamily;
use crate::types::AuthoredNode;

/// The families `raw` declares, each `name_pattern` compiled by the native matcher.
pub fn parse_dynamic_columns<N: AuthoredNode>(
    raw: &N,
    model: (&str, &str),
) -> Result<Vec<DynamicFamily>, ConfigError> {
    let (model_name, path) = model;
    dynamic_families(raw, &DynamicSource { model_name, path })
}
