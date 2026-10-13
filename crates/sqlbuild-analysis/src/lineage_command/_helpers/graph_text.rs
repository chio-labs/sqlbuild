//! Human relation lineage: edge lists, dependency trees and graph summaries.

use std::collections::{HashMap, HashSet};
use std::convert::Infallible;

use sqlbuild_core::cli_text::models::CliStyle;

use crate::lineage_command::constants::{
    ALREADY_SHOWN, BOTH_DIRECTIONS, DOWNSTREAM_DIRECTION, UPSTREAM_DIRECTION,
};
use crate::lineage_command::models::{LineageGraph, LineageKey, LineageNode};
use crate::lineage_graph::main::tree_lines::tree_lines;
use crate::lineage_graph::models::TreeLine;
use crate::lineage_graph::types::TreeVisitor;

/// `type:name`.
pub(crate) fn node_id(key: &LineageKey) -> String {
    format!("{}:{}", key.resource_type, key.name)
}

fn format_key(key: &LineageKey, style: CliStyle) -> String {
    format!(
        "{}:{}",
        style.muted(&key.resource_type),
        style.section(&key.name)
    )
}

fn format_node(node: &LineageNode, style: CliStyle) -> String {
    let mut parts: Vec<String> = vec![
        style.muted(&node.key.resource_type),
        style.section(&node.key.name),
    ];
    if let Some(path) = &node.relative_path {
        parts.push(style.muted(path));
    }
    parts.join("  ")
}

/// The graph as `upstream -> downstream` lines, or its nodes when it has no edges.
pub(crate) fn graph_list(graph: &LineageGraph, style: CliStyle) -> String {
    if graph.edges.is_empty() {
        return graph
            .nodes
            .iter()
            .map(|node| format_key(&node.key, style))
            .collect::<Vec<_>>()
            .join("\n");
    }
    let width: usize = graph
        .edges
        .iter()
        .map(|(upstream, _)| node_id(upstream).chars().count())
        .max()
        .unwrap_or(0);
    graph
        .edges
        .iter()
        .map(|(upstream, downstream)| {
            format!(
                "{}{} {} {}",
                format_key(upstream, style),
                " ".repeat(width - node_id(upstream).chars().count()),
                style.muted("->"),
                format_key(downstream, style)
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// A tree around the single focus node, or a summary of any other graph.
pub(crate) fn graph_tree(graph: &LineageGraph, style: CliStyle) -> String {
    let (Some(direction), [focus]) = (graph.direction.as_deref(), graph.focus_keys.as_slice())
    else {
        return graph_summary(graph, style);
    };
    let nodes: HashMap<&LineageKey, &LineageNode> =
        graph.nodes.iter().map(|node| (&node.key, node)).collect();
    let focus_text: String = nodes
        .get(focus)
        .map_or_else(String::new, |node| format_node(node, style));
    let mut lines: Vec<String> = vec![format!(
        "{}  {focus_text}  {}",
        style.title("Lineage"),
        style.muted(direction)
    )];
    let sections: [(&str, bool); 2] = [(UPSTREAM_DIRECTION, true), (DOWNSTREAM_DIRECTION, false)];
    for (section, upstream) in sections {
        if direction != section && direction != BOTH_DIRECTIONS {
            continue;
        }
        let mut deps: HashMap<&LineageKey, Vec<&LineageKey>> = HashMap::new();
        for (parent, child) in &graph.edges {
            let (from, to) = if upstream {
                (child, parent)
            } else {
                (parent, child)
            };
            deps.entry(from).or_default().push(to);
        }
        if direction == BOTH_DIRECTIONS {
            lines.push(style.section(section));
        }
        let mut tree = DependencyTree {
            deps: &deps,
            nodes: &nodes,
            style,
            lines: Vec::new(),
        };
        let roots: Vec<&LineageKey> = tree.sorted_children(focus);
        let Ok(()) = tree_lines(roots, HashSet::from([focus]), &mut tree);
        lines.extend(tree.lines);
    }
    lines.join("\n")
}

fn graph_summary(graph: &LineageGraph, style: CliStyle) -> String {
    let mut lines: Vec<String> = vec![format!(
        "{}  {}",
        style.title("Lineage graph"),
        style.muted(&format!(
            "({} nodes, {} edges)",
            graph.nodes.len(),
            graph.edges.len()
        ))
    )];
    if graph.edges.is_empty() {
        lines.extend(
            graph
                .nodes
                .iter()
                .map(|node| format!("  {}", format_node(node, style))),
        );
    } else {
        lines.extend(graph.edges.iter().map(|(parent, child)| {
            format!(
                "{}{} {} {}",
                style.muted("  - "),
                format_key(parent, style),
                style.muted("->"),
                format_key(child, style)
            )
        }));
    }
    lines.join("\n")
}

/// Dependency nodes shown once each, children sorted by type and name.
struct DependencyTree<'a> {
    deps: &'a HashMap<&'a LineageKey, Vec<&'a LineageKey>>,
    nodes: &'a HashMap<&'a LineageKey, &'a LineageNode>,
    style: CliStyle,
    lines: Vec<String>,
}

impl<'a> DependencyTree<'a> {
    fn sorted_children(&self, key: &LineageKey) -> Vec<&'a LineageKey> {
        let mut children: Vec<&'a LineageKey> = self.deps.get(key).cloned().unwrap_or_default();
        children.sort();
        children
    }
}

impl<'a> TreeVisitor<&'a LineageKey, &'a LineageKey, Infallible> for DependencyTree<'a> {
    fn key(&mut self, node: &&'a LineageKey) -> Result<&'a LineageKey, Infallible> {
        Ok(*node)
    }

    fn line(&mut self, line: TreeLine<'_, &'a LineageKey>) -> Result<(), Infallible> {
        let suffix: String = if line.repeated {
            self.style.muted(ALREADY_SHOWN)
        } else {
            String::new()
        };
        let node: String = self
            .nodes
            .get(*line.node)
            .map_or_else(String::new, |node| format_node(node, self.style));
        self.lines.push(format!(
            "{}{node}{suffix}",
            self.style.muted(&format!("{}{}", line.prefix, line.branch))
        ));
        Ok(())
    }

    fn children(&mut self, node: &&'a LineageKey) -> Result<Vec<&'a LineageKey>, Infallible> {
        Ok(self.sorted_children(node))
    }
}
