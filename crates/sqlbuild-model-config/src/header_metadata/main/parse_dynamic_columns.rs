//! Parse one MODEL header's `dynamic_columns`, with the errors Python raises.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::dynamic::{DynamicSource, dynamic_families};
use crate::header_metadata::models::DynamicFamily;
use crate::types::AuthoredNode;

/// The families `raw` declares; `pattern_error` compiles a `name_pattern` in the runtime dialect.
pub fn parse_dynamic_columns<N: AuthoredNode>(
    raw: &N,
    model: (&str, &str),
    pattern_error: &dyn Fn(&str) -> Option<String>,
) -> Result<Vec<DynamicFamily>, ConfigError> {
    let (model_name, path) = model;
    dynamic_families(
        raw,
        &DynamicSource {
            model_name,
            path,
            pattern_error,
        },
    )
}
