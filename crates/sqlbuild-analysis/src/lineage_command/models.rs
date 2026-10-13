//! Relation lineage indexes, selected graphs, column traces and semantic uses.

use std::collections::HashMap;

/// A project resource: its type as Python's `str()` renders it, and its name.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct LineageKey {
    pub resource_type: String,
    pub name: String,
}

/// One displayable resource.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LineageNode {
    pub key: LineageKey,
    pub relative_path: Option<String>,
    pub qualified_name: Option<String>,
}

/// The structural project graph relation lineage reads, every collection in Python dict order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LineageIndex {
    pub nodes: HashMap<LineageKey, LineageNode>,
    pub upstream: Vec<(LineageKey, Vec<LineageKey>)>,
    pub downstream: Vec<(LineageKey, Vec<LineageKey>)>,
    pub tags: Vec<(String, Vec<LineageKey>)>,
    pub paths: Vec<(LineageKey, String)>,
    pub all_keys: Vec<(String, LineageKey)>,
}

/// A selected slice of the relation graph.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LineageGraph {
    pub nodes: Vec<LineageNode>,
    pub edges: Vec<(LineageKey, LineageKey)>,
    pub focus_keys: Vec<LineageKey>,
    pub direction: Option<String>,
}

/// One positional target, `[kind:]<name>` or `[kind:]<model>.<column>`, resolved by name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LineageTarget {
    pub kind: Option<String>,
    pub name: String,
    pub key: Option<LineageKey>,
    pub column_name: Option<String>,
    pub kind_matches: bool,
}

/// Selector anchors depth trimming starts from.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LineageAnchors {
    pub upstream: Vec<LineageKey>,
    pub downstream: Vec<LineageKey>,
    pub retained: Vec<LineageKey>,
}

/// A resource-qualified column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LineageColumn {
    pub resource_type: String,
    pub resource_name: String,
    pub column_name: String,
}

/// One column lineage edge.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LineageColumnEdge {
    pub source: LineageColumn,
    pub target: LineageColumn,
    pub transform: String,
    pub confidence: String,
}

/// A traced column and the edges reached from it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ColumnTrace {
    pub target: LineageColumn,
    pub trace: Vec<LineageColumnEdge>,
    pub direction: String,
    pub mode: String,
    pub max_depth: Option<i64>,
    pub analyzed_model_count: usize,
    pub truncated: bool,
}

/// The models a column trace analyses, and whether the depth limit hid more.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ColumnCandidates {
    pub model_names: Vec<String>,
    pub truncated: bool,
}

/// One direct non-projection use of a resource column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SemanticUse {
    pub consumer_model: String,
    pub context: String,
    pub expression: String,
    pub source: LineageColumn,
    pub confidence: String,
    pub line: Option<i64>,
    pub column: Option<i64>,
}

/// The command options request validation reads.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LineageRequestShape {
    pub targets: Vec<String>,
    pub select: Vec<String>,
    pub exclude: Vec<String>,
}

/// Rendered lineage before printing: JSON stays a value so semantic uses can join it.
#[derive(Clone, Debug, PartialEq)]
pub enum LineageRendering {
    Json(sqlbuild_core::json::models::JsonValue),
    Text(String),
}
