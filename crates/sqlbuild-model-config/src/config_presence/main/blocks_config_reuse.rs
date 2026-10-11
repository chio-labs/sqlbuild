//! Whether model header metadata keeps a model from reusing another model's config.

use crate::config_presence::_helpers::reuse::blocks_reuse;
use crate::types::AuthoredNode;

/// Whether `value` holds a template, a macro call, a non-string key or an unsupported value.
pub fn blocks_config_reuse<N: AuthoredNode>(value: &N) -> bool {
    blocks_reuse(value)
}
