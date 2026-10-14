//! Memoized identity resolution over one dependency graph, each node once.

use std::collections::{HashMap, HashSet};

use crate::planner_identity::_helpers::compose_graph_identity::compose_graph_identity;
use crate::planner_identity::models::{GraphKey, IdentityNode};
use crate::planner_identity::types::IdentityHashes;

/// Which hashes a resolution composes from.
#[derive(Clone, Copy)]
enum Mode {
    Expected,
    Write,
}

/// Expected or selected-write identity resolution state.
pub(crate) struct IdentityResolver<'a> {
    nodes: &'a HashMap<GraphKey, IdentityNode>,
    selected: Option<&'a HashSet<GraphKey>>,
    hashes: IdentityHashes,
    positions: HashMap<GraphKey, usize>,
    resolved_selected: HashMap<GraphKey, String>,
    visiting: HashSet<GraphKey>,
}

impl<'a> IdentityResolver<'a> {
    pub(crate) fn new(
        nodes: &'a HashMap<GraphKey, IdentityNode>,
        selected: Option<&'a HashSet<GraphKey>>,
        base_hashes: Vec<(GraphKey, String)>,
    ) -> Self {
        let mut resolver = Self {
            nodes,
            selected,
            hashes: Vec::new(),
            positions: HashMap::new(),
            resolved_selected: HashMap::new(),
            visiting: HashSet::new(),
        };
        for (key, hash) in base_hashes {
            resolver.record(&key, Some(hash));
        }
        resolver
    }

    /// Every hash recorded so far, in first-recorded order.
    pub(crate) fn into_hashes(self) -> IdentityHashes {
        self.hashes
    }

    /// A node's expected hash, composed from its upstream expected hashes.
    pub(crate) fn resolve_expected(&mut self, key: &GraphKey) -> Option<String> {
        if let Some(position) = self.positions.get(key) {
            return self.hashes[*position].1.clone();
        }
        let nodes: &'a HashMap<GraphKey, IdentityNode> = self.nodes;
        let Some((node, local_hash)) = nodes
            .get(key)
            .and_then(|node| node.local_hash.as_deref().map(|local| (node, local)))
        else {
            self.record(key, None);
            return None;
        };
        if self.visiting.contains(key) {
            self.record(key, Some(local_hash.to_owned()));
            return Some(local_hash.to_owned());
        }
        let composed: String = self.compose(key, (node, local_hash), Mode::Expected);
        self.record(key, Some(composed.clone()));
        Some(composed)
    }

    /// A selected node's hash recomputed from upstream write hashes; other nodes keep theirs.
    pub(crate) fn resolve_write(&mut self, key: &GraphKey) -> Option<String> {
        if !self.selected.is_some_and(|selected| selected.contains(key)) {
            return self.recorded(key);
        }
        if let Some(hash) = self.resolved_selected.get(key) {
            return Some(hash.clone());
        }
        let nodes: &'a HashMap<GraphKey, IdentityNode> = self.nodes;
        let Some((node, local_hash)) = nodes
            .get(key)
            .and_then(|node| node.local_hash.as_deref().map(|local| (node, local)))
        else {
            return self.recorded(key);
        };
        if self.visiting.contains(key) {
            return Some(local_hash.to_owned());
        }
        let composed: String = self.compose(key, (node, local_hash), Mode::Write);
        self.record(key, Some(composed.clone()));
        self.resolved_selected.insert(key.clone(), composed.clone());
        Some(composed)
    }

    fn compose(
        &mut self,
        key: &GraphKey,
        (node, local_hash): (&IdentityNode, &str),
        mode: Mode,
    ) -> String {
        self.visiting.insert(key.clone());
        let mut upstream_hashes: Vec<String> = Vec::new();
        for upstream_key in &node.upstream_keys {
            let upstream_hash: Option<String> = match mode {
                Mode::Expected => self.resolve_expected(upstream_key),
                Mode::Write => self.resolve_write(upstream_key),
            };
            upstream_hashes.extend(upstream_hash);
        }
        self.visiting.remove(key);
        let upstream: Vec<&str> = upstream_hashes.iter().map(String::as_str).collect();
        compose_graph_identity(local_hash, &upstream)
    }

    fn recorded(&self, key: &GraphKey) -> Option<String> {
        self.positions
            .get(key)
            .and_then(|position| self.hashes[*position].1.clone())
    }

    fn record(&mut self, key: &GraphKey, hash: Option<String>) {
        match self.positions.get(key) {
            Some(position) => self.hashes[*position].1 = hash,
            None => {
                self.positions.insert(key.clone(), self.hashes.len());
                self.hashes.push((key.clone(), hash));
            }
        }
    }
}
