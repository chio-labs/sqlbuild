//! `json_meta_problem`: why an authored audit `meta` value is not a mapping of JSON values.

use crate::types::{AuthoredNode, NodeKind};

/// The first reason `meta` is not a string-keyed mapping of JSON values, or `None` when it is.
pub fn json_meta_problem<N: AuthoredNode>(meta: &N) -> Option<String> {
    if meta.kind() != NodeKind::Map {
        return Some(format!(
            "must be a mapping of JSON values, got {}",
            meta.python_repr()
        ));
    }
    mapping_problem(meta, "meta")
        .map(|problem| format!("must map string keys to JSON values; {problem}"))
}

fn mapping_problem<N: AuthoredNode>(node: &N, path: &str) -> Option<String> {
    for (key, value) in node.entries() {
        let Some(name) = key.text() else {
            return Some(format!(
                "key {} in {path} is not a string",
                key.python_repr()
            ));
        };
        if let Some(problem) = value_problem(&value, &format!("{path}['{name}']")) {
            return Some(problem);
        }
    }
    None
}

fn value_problem<N: AuthoredNode>(node: &N, path: &str) -> Option<String> {
    match node.kind() {
        NodeKind::Null | NodeKind::Bool(_) | NodeKind::Int { .. } | NodeKind::Str => None,
        NodeKind::List | NodeKind::Tuple => node
            .items()
            .iter()
            .enumerate()
            .find_map(|(index, item)| value_problem(item, &format!("{path}[{index}]"))),
        NodeKind::Map => mapping_problem(node, path),
        NodeKind::Other => match node.number() {
            Some(number) if number.is_finite() => None,
            _ => Some(format!(
                "{path} is not JSON-serialisable: {}",
                node.python_repr()
            )),
        },
    }
}
