//! JSON payloads of relation graphs, column traces and semantic uses.

use sqlbuild_core::json::models::{JsonInteger, JsonValue};

use crate::lineage_command::_helpers::graph_text::node_id;
use crate::lineage_command::models::{
    ColumnTrace, LineageColumn, LineageColumnEdge, LineageGraph, LineageNode, SemanticUse,
};

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn object(entries: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        entries
            .into_iter()
            .map(|(name, value)| (name.to_owned(), value))
            .collect(),
    )
}

fn integer(value: Option<i64>) -> JsonValue {
    value.map_or(JsonValue::Null, |value| {
        JsonValue::Integer(JsonInteger::from(value))
    })
}

fn node(node: &LineageNode) -> JsonValue {
    let mut entries: Vec<(&str, JsonValue)> = vec![
        ("id", text(&node_id(&node.key))),
        ("name", text(&node.key.name)),
        ("resource_type", text(&node.key.resource_type)),
    ];
    if let Some(path) = &node.relative_path {
        entries.push(("relative_path", text(path)));
    }
    if let Some(name) = &node.qualified_name {
        entries.push(("qualified_name", text(name)));
    }
    object(entries)
}

/// The selected graph's nodes, edges, focus and direction.
pub(crate) fn graph_json(graph: &LineageGraph) -> JsonValue {
    let mut entries: Vec<(&str, JsonValue)> = vec![
        (
            "nodes",
            JsonValue::Array(graph.nodes.iter().map(node).collect()),
        ),
        (
            "edges",
            JsonValue::Array(
                graph
                    .edges
                    .iter()
                    .map(|(upstream, downstream)| {
                        object(vec![
                            ("from", text(&node_id(upstream))),
                            ("to", text(&node_id(downstream))),
                        ])
                    })
                    .collect(),
            ),
        ),
    ];
    if !graph.focus_keys.is_empty() {
        entries.push((
            "focus",
            JsonValue::Array(
                graph
                    .focus_keys
                    .iter()
                    .map(|key| text(&node_id(key)))
                    .collect(),
            ),
        ));
    }
    if let Some(direction) = &graph.direction {
        entries.push(("direction", text(direction)));
    }
    object(entries)
}

fn column(column: &LineageColumn) -> JsonValue {
    object(vec![
        ("resource_type", text(&column.resource_type)),
        ("resource_name", text(&column.resource_name)),
        ("column_name", text(&column.column_name)),
    ])
}

fn edge(edge: &LineageColumnEdge) -> JsonValue {
    object(vec![
        ("source", column(&edge.source)),
        ("target", column(&edge.target)),
        ("transform", text(&edge.transform)),
        ("confidence", text(&edge.confidence)),
    ])
}

/// The traced column, its trace and the analysis metadata.
pub(crate) fn trace_json(trace: &ColumnTrace) -> JsonValue {
    object(vec![
        ("target", column(&trace.target)),
        ("direction", text(&trace.direction)),
        (
            "metadata",
            object(vec![
                ("mode", text(&trace.mode)),
                ("max_depth", integer(trace.max_depth)),
                (
                    "analyzed_models",
                    integer(i64::try_from(trace.analyzed_model_count).ok()),
                ),
                ("truncated", JsonValue::Bool(trace.truncated)),
            ]),
        ),
        (
            "trace",
            JsonValue::Array(trace.trace.iter().map(edge).collect()),
        ),
    ])
}

/// One semantic use's payload.
pub(crate) fn use_json(semantic_use: &SemanticUse) -> JsonValue {
    object(vec![
        ("consumer_model", text(&semantic_use.consumer_model)),
        ("context", text(&semantic_use.context)),
        ("expression", text(&semantic_use.expression)),
        (
            "source",
            object(vec![
                ("resource_type", text(&semantic_use.source.resource_type)),
                ("resource_name", text(&semantic_use.source.resource_name)),
                ("column", text(&semantic_use.source.column_name)),
            ]),
        ),
        ("confidence", text(&semantic_use.confidence)),
        ("line", integer(semantic_use.line)),
        ("column", integer(semantic_use.column)),
    ])
}
