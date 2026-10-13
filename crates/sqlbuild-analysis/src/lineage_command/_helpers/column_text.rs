//! Human column lineage: dependency lists and column-trace trees.

use std::collections::{HashMap, HashSet};
use std::convert::Infallible;

use sqlbuild_core::cli_text::models::CliStyle;

use crate::lineage_command::constants::{
    ALREADY_SHOWN, DOWNSTREAM_DIRECTION, HUMAN_COLUMN_TRACE_LIMIT, STAR_TRANSFORM,
    STAR_TRANSFORM_LABEL,
};
use crate::lineage_command::models::{ColumnTrace, LineageColumn, LineageColumnEdge};
use crate::lineage_graph::main::trace_limit_note::trace_limit_note;
use crate::lineage_graph::main::tree_lines::tree_lines;
use crate::lineage_graph::models::TreeLine;
use crate::lineage_graph::types::TreeVisitor;

/// `resource.column`.
fn column_id(column: &LineageColumn) -> String {
    format!("{}.{}", column.resource_name, column.column_name)
}

fn transform_label(edge: &LineageColumnEdge) -> &str {
    if edge.transform == STAR_TRANSFORM {
        STAR_TRANSFORM_LABEL
    } else {
        &edge.transform
    }
}

fn displayed(trace: &ColumnTrace) -> &[LineageColumnEdge] {
    &trace.trace[..trace.trace.len().min(HUMAN_COLUMN_TRACE_LIMIT)]
}

fn limit_note(trace: &ColumnTrace, style: CliStyle) -> Vec<String> {
    let notes: Vec<String> = trace_limit_note(
        i64::try_from(trace.trace.len()).unwrap_or(i64::MAX),
        i64::try_from(HUMAN_COLUMN_TRACE_LIMIT).unwrap_or(i64::MAX),
    );
    if notes.is_empty() {
        return notes;
    }
    let mut lines: Vec<String> = vec![String::new()];
    lines.extend(notes.iter().map(|note| style.muted(note)));
    lines
}

/// The trace as `source -> target  transform` lines.
pub(crate) fn column_list(trace: &ColumnTrace, style: CliStyle) -> String {
    if trace.trace.is_empty() {
        return format!(
            "Column dependencies\n\n{}",
            style.section(&column_id(&trace.target))
        );
    }
    let edges: &[LineageColumnEdge] = displayed(trace);
    let width = |side: fn(&LineageColumnEdge) -> &LineageColumn| -> usize {
        edges
            .iter()
            .map(|edge| column_id(side(edge)).chars().count())
            .max()
            .unwrap_or(0)
    };
    let left: usize = width(|edge| &edge.source);
    let right: usize = width(|edge| &edge.target);
    let mut lines: Vec<String> = vec![style.title("Column dependencies"), String::new()];
    for edge in edges {
        let source: String = column_id(&edge.source);
        let target: String = column_id(&edge.target);
        lines.push(format!(
            "{}{} {} {}{} {}",
            style.section(&source),
            " ".repeat(left - source.chars().count()),
            style.muted("->"),
            style.section(&target),
            " ".repeat(right - target.chars().count()),
            style.muted(transform_label(edge))
        ));
    }
    lines.extend(limit_note(trace, style));
    lines.join("\n")
}

/// The trace as a tree from the target column.
pub(crate) fn column_tree(trace: &ColumnTrace, style: CliStyle) -> String {
    let target: String = column_id(&trace.target);
    let mut lines: Vec<String> = vec![
        format!(
            "{}  {}  {}",
            style.title("Column trace"),
            style.section(&target),
            style.muted(&trace.direction)
        ),
        String::new(),
    ];
    if trace.trace.is_empty() {
        lines.push(style.muted("  No column dependencies found"));
        return lines.join("\n");
    }
    let downstream: bool = trace.direction == DOWNSTREAM_DIRECTION;
    let mut deps: HashMap<String, Vec<&LineageColumnEdge>> = HashMap::new();
    for edge in displayed(trace) {
        let key: &LineageColumn = if downstream {
            &edge.source
        } else {
            &edge.target
        };
        deps.entry(column_id(key)).or_default().push(edge);
    }
    let mut tree = ColumnTree {
        deps: &deps,
        downstream,
        style,
        lines: Vec::new(),
    };
    let roots: Vec<&LineageColumnEdge> = tree.sorted_edges(&target);
    let Ok(()) = tree_lines(roots, HashSet::from([target]), &mut tree);
    lines.extend(tree.lines);
    lines.extend(limit_note(trace, style));
    lines.join("\n")
}

/// Column-trace edges shown once per related column, sorted by that column.
struct ColumnTree<'a> {
    deps: &'a HashMap<String, Vec<&'a LineageColumnEdge>>,
    downstream: bool,
    style: CliStyle,
    lines: Vec<String>,
}

impl<'a> ColumnTree<'a> {
    fn related_id(&self, edge: &LineageColumnEdge) -> String {
        column_id(if self.downstream {
            &edge.target
        } else {
            &edge.source
        })
    }

    fn sorted_edges(&self, id: &str) -> Vec<&'a LineageColumnEdge> {
        let mut edges: Vec<&'a LineageColumnEdge> = self.deps.get(id).cloned().unwrap_or_default();
        edges.sort_by_cached_key(|edge| self.related_id(edge));
        edges
    }
}

impl<'a> TreeVisitor<&'a LineageColumnEdge, String, Infallible> for ColumnTree<'a> {
    fn key(&mut self, edge: &&'a LineageColumnEdge) -> Result<String, Infallible> {
        Ok(self.related_id(edge))
    }

    fn line(&mut self, line: TreeLine<'_, &'a LineageColumnEdge>) -> Result<(), Infallible> {
        let suffix: String = if line.repeated {
            self.style.muted(ALREADY_SHOWN)
        } else {
            String::new()
        };
        let edge: &LineageColumnEdge = line.node;
        self.lines.push(format!(
            "{}{}{} {}{suffix}",
            line.prefix,
            self.style.muted(line.branch),
            self.style.section(&self.related_id(edge)),
            self.style.muted(&format!("({})", transform_label(edge)))
        ));
        Ok(())
    }

    fn children(
        &mut self,
        edge: &&'a LineageColumnEdge,
    ) -> Result<Vec<&'a LineageColumnEdge>, Infallible> {
        Ok(self.sorted_edges(&self.related_id(edge)))
    }
}
