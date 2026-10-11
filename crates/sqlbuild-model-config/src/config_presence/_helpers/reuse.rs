//! Python's checks deciding whether a model's config can be reused across models.

use crate::config_presence::_helpers::macro_calls::macro_call;
use crate::config_presence::_helpers::template_tokens::template_token;
use crate::types::{AuthoredNode, NodeKind};

/// `_contains_dynamic_or_unsupported_reusable_metadata`.
pub(crate) fn blocks_reuse<N: AuthoredNode>(node: &N) -> bool {
    match node.kind() {
        NodeKind::Str => node
            .with_text(|text| template_token(text) || macro_call(text))
            .unwrap_or(false),
        NodeKind::Map => node
            .entries()
            .iter()
            .any(|(key, value)| key.kind() != NodeKind::Str || blocks_reuse(value)),
        NodeKind::List | NodeKind::Tuple => node.items().iter().any(blocks_reuse),
        NodeKind::Null | NodeKind::Bool(_) | NodeKind::Int { .. } => false,
        NodeKind::Other => node.number().is_none(),
    }
}

/// `_contains_mutable_nested_config`'s `is_mutable`.
pub(crate) fn mutable<N: AuthoredNode>(node: &N) -> bool {
    match node.kind() {
        NodeKind::Map | NodeKind::List => true,
        NodeKind::Tuple => node.items().iter().any(mutable),
        NodeKind::Null | NodeKind::Bool(_) | NodeKind::Int { .. } | NodeKind::Str => false,
        NodeKind::Other => node.number().is_none(),
    }
}
