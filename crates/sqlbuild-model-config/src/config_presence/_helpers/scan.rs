//! The recursive config scan shared by every presence check.

use crate::types::{AuthoredNode, NodeKind};

/// Scan mapping values, list and tuple items and strings like Python's recursive config scans.
pub(crate) fn scan<N: AuthoredNode>(node: &N, text_presence: &impl Fn(&str) -> bool) -> bool {
    match node.kind() {
        NodeKind::Str => node.with_text(text_presence).unwrap_or(false),
        NodeKind::Map => node
            .entries()
            .iter()
            .any(|(_, value)| scan(value, text_presence)),
        NodeKind::List | NodeKind::Tuple => {
            node.items().iter().any(|item| scan(item, text_presence))
        }
        _ => false,
    }
}
