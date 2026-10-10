//! Recursive template presence over authored config values.

use crate::config_presence::_helpers::scan::scan;
use crate::config_presence::_helpers::template_tokens::template_token;
use crate::types::AuthoredNode;

/// Return whether `contains_template_data` finds `${` in any nested string.
pub fn contains_template<N: AuthoredNode>(node: &N) -> bool {
    scan(node, &template_token)
}
