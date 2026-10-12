//! Latest fingerprint rows indexed by identity and by node name.

use std::collections::HashMap;

use crate::fingerprint_storage::constants::NODE_TYPE_MODEL;
use crate::fingerprint_storage::models::{FingerprintIdentity, LatestIndex};

/// Kept row positions in Python dict order, a model winning a node-name collision.
pub fn latest_index(identities: &[FingerprintIdentity<'_>]) -> LatestIndex {
    let mut by_name: Vec<usize> = Vec::new();
    let mut name_slots: HashMap<&str, usize> = HashMap::new();
    let mut by_identity: Vec<usize> = Vec::new();
    let mut identity_slots: HashMap<(&str, &str), usize> = HashMap::new();
    for (position, identity) in identities.iter().enumerate() {
        let key = (identity.node_type, identity.node_name);
        match identity_slots.get(&key) {
            Some(&slot) => by_identity[slot] = position,
            None => {
                let _ = identity_slots.insert(key, by_identity.len());
                by_identity.push(position);
            }
        }
        match name_slots.get(identity.node_name) {
            Some(&slot) => {
                if identity.node_type == NODE_TYPE_MODEL {
                    by_name[slot] = position;
                }
            }
            None => {
                let _ = name_slots.insert(identity.node_name, by_name.len());
                by_name.push(position);
            }
        }
    }
    LatestIndex {
        by_name,
        by_identity,
    }
}
