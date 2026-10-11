//! Whether an inherited config value is mutable, which keeps its config from being reused.

use crate::config_presence::_helpers::reuse::mutable;
use crate::types::AuthoredNode;

/// Whether `value` is a mapping, list, set or other object, or a tuple holding one.
pub fn mutable_config_value<N: AuthoredNode>(value: &N) -> bool {
    mutable(value)
}
