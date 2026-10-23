//! The snapshot key of one node.

/// `kind:identity`, where identity is a name, or a declaration identity for scoped declarations.
pub fn node_key(kind: &str, identity: &str) -> String {
    format!("{kind}:{identity}")
}
