//! Memoized identity resolution over one dependency graph, each node once, with an explicit stack.

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

/// A node whose upstream hashes are being resolved.
struct Frame<'a> {
    key: &'a GraphKey,
    node: &'a IdentityNode,
    local_hash: &'a str,
    next_upstream: usize,
    upstream_hashes: Vec<String>,
}

/// What entering a node yields: its hash already, or a frame to resolve.
enum Entered<'a> {
    Resolved(Option<String>),
    Pending(Frame<'a>),
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
    pub(crate) fn resolve_expected(&mut self, key: &'a GraphKey) -> Option<String> {
        self.resolve(key, Mode::Expected)
    }

    /// A selected node's hash recomputed from upstream write hashes; other nodes keep theirs.
    pub(crate) fn resolve_write(&mut self, key: &'a GraphKey) -> Option<String> {
        self.resolve(key, Mode::Write)
    }

    fn resolve(&mut self, root: &'a GraphKey, mode: Mode) -> Option<String> {
        let mut stack: Vec<Frame<'a>> = match self.enter(root, mode) {
            Entered::Resolved(hash) => return hash,
            Entered::Pending(frame) => vec![frame],
        };
        while let Some(frame) = stack.last_mut() {
            if let Some(upstream_key) = frame.node.upstream_keys.get(frame.next_upstream) {
                frame.next_upstream += 1;
                match self.enter(upstream_key, mode) {
                    Entered::Resolved(hash) => frame.upstream_hashes.extend(hash),
                    Entered::Pending(upstream_frame) => stack.push(upstream_frame),
                }
                continue;
            }
            let Some(finished) = stack.pop() else {
                break;
            };
            let composed: String = self.finish(&finished, mode);
            match stack.last_mut() {
                Some(parent) => parent.upstream_hashes.push(composed),
                None => return Some(composed),
            }
        }
        None
    }

    fn enter(&mut self, key: &'a GraphKey, mode: Mode) -> Entered<'a> {
        if let Mode::Write = mode {
            if !self.selected.is_some_and(|selected| selected.contains(key)) {
                return Entered::Resolved(self.recorded(key));
            }
            if let Some(hash) = self.resolved_selected.get(key) {
                return Entered::Resolved(Some(hash.clone()));
            }
        } else if let Some(position) = self.positions.get(key) {
            return Entered::Resolved(self.hashes[*position].1.clone());
        }
        let nodes: &'a HashMap<GraphKey, IdentityNode> = self.nodes;
        let Some((node, local_hash)) = nodes
            .get(key)
            .and_then(|node| node.local_hash.as_deref().map(|local| (node, local)))
        else {
            return Entered::Resolved(match mode {
                Mode::Expected => {
                    self.record(key, None);
                    None
                }
                Mode::Write => self.recorded(key),
            });
        };
        if self.visiting.contains(key) {
            if let Mode::Expected = mode {
                self.record(key, Some(local_hash.to_owned()));
            }
            return Entered::Resolved(Some(local_hash.to_owned()));
        }
        self.visiting.insert(key.clone());
        Entered::Pending(Frame {
            key,
            node,
            local_hash,
            next_upstream: 0,
            upstream_hashes: Vec::new(),
        })
    }

    fn finish(&mut self, frame: &Frame<'a>, mode: Mode) -> String {
        self.visiting.remove(frame.key);
        let upstream: Vec<&str> = frame.upstream_hashes.iter().map(String::as_str).collect();
        let composed: String = compose_graph_identity(frame.local_hash, &upstream);
        self.record(frame.key, Some(composed.clone()));
        if let Mode::Write = mode {
            self.resolved_selected
                .insert(frame.key.clone(), composed.clone());
        }
        composed
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
