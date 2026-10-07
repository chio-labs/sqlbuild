//! The recursive config scan shared by every presence check.

use crate::config_presence::models::Presence;
use crate::types::{AuthoredNode, NodeKind};

/// Scan mapping values, list and tuple items and strings like Python's recursive config scans.
pub(crate) fn scan<N: AuthoredNode>(
    node: &N,
    text_presence: &impl Fn(&str) -> Presence,
) -> Presence {
    match node.kind() {
        NodeKind::Str => node.with_text(text_presence).unwrap_or(Presence::Deferred),
        NodeKind::Map => any_present(node.entries().iter().map(|(_, value)| value), text_presence),
        NodeKind::List | NodeKind::Tuple => any_present(node.items().iter(), text_presence),
        _ => Presence::Absent,
    }
}

fn any_present<'node, N: AuthoredNode + 'node>(
    nodes: impl Iterator<Item = &'node N>,
    text_presence: &impl Fn(&str) -> Presence,
) -> Presence {
    let mut deferred = false;
    for node in nodes {
        match scan(node, text_presence) {
            Presence::Present => return Presence::Present,
            Presence::Deferred => deferred = true,
            Presence::Absent => {}
        }
    }
    if deferred {
        Presence::Deferred
    } else {
        Presence::Absent
    }
}
