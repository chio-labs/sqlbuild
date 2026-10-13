//! The sections of the terminal diff summary, as layout nodes.

use std::collections::BTreeMap;

use crate::diff_report::_helpers::evidence::{
    display_example_value, render_example_pair, render_key_value,
};
use crate::diff_report::_helpers::findings::has_schema_differences;
use crate::diff_report::_helpers::layout::{BoxChars, Column, Justify, Node, Style, Table, column};
use crate::diff_report::_helpers::numbers::{grouped, percent, percentage};
use crate::diff_report::constants::{
    CHANGED_COLUMN_NAME_WIDTH, QUERY_INPUT_KIND, TOP_CHANGED_COLUMNS,
};
use crate::diff_report::models::{
    DiffColumnFacts, DiffCoverageFacts, DiffExampleOptions, DiffModelFacts, DiffRowFacts,
    DiffTextOptions,
};
use crate::diff_report::types::DiffNamedValue;

pub(crate) const BOLD: Style = Style {
    bold: true,
    ..Style::PLAIN
};
pub(crate) const OBJECT: Style = Style {
    bold: true,
    color: 36,
    ..Style::PLAIN
};
pub(crate) const MUTED: Style = Style {
    dim: true,
    ..Style::PLAIN
};
const ITALIC: Style = Style {
    italic: true,
    ..Style::PLAIN
};
const ADDED: Style = Style {
    color: 32,
    ..Style::PLAIN
};
const REMOVED: Style = Style {
    color: 31,
    ..Style::PLAIN
};
const WARNING: Style = Style {
    color: 33,
    ..Style::PLAIN
};

const HEAVY_EDGE: BoxChars = BoxChars {
    top: ['┏', '━', '┯', '┓'],
    row: ['┃', ' ', '│', '┃'],
    separator: ['┠', '─', '┼', '┨'],
    bottom: ['┗', '━', '┷', '┛'],
};
const ROUNDED: BoxChars = BoxChars {
    top: ['╭', '─', '┬', '╮'],
    row: ['│', ' ', '│', '│'],
    separator: ['├', '─', '┼', '┤'],
    bottom: ['╰', '─', '┴', '╯'],
};
const SQUARE: BoxChars = BoxChars {
    top: ['┌', '─', '┬', '┐'],
    row: ['│', ' ', '│', '│'],
    separator: ['├', '─', '┼', '┤'],
    bottom: ['└', '─', '┴', '┘'],
};

/// Everything one model section needs besides the model itself.
pub(crate) struct SectionContext<'a> {
    pub(crate) from_label: &'a str,
    pub(crate) to_label: &'a str,
    pub(crate) text: &'a DiffTextOptions,
    pub(crate) examples: DiffExampleOptions,
}

fn boxed(columns: Vec<Column>, borders: BoxChars, padding: (usize, usize)) -> Table {
    Table {
        columns,
        rows: Vec::new(),
        section_after: Vec::new(),
        borders: Some(borders),
        padding,
        collapse_padding: false,
        pad_edge: true,
    }
}

fn texts(values: &[String]) -> Vec<Node> {
    values
        .iter()
        .map(|value| Node::plain(value.clone()))
        .collect()
}

/// The printed nodes of one model: overview and every section.
pub(crate) fn model_nodes(model: &DiffModelFacts, context: &SectionContext<'_>) -> Vec<Node> {
    let mut nodes: Vec<Node> = vec![overview(model, &context.text.mode_label), Node::plain("")];
    nodes.extend(section("Schemas", schema_summary(model)));
    let Some(rows) = &model.rows else {
        return nodes;
    };
    nodes.extend(section("Coverage", coverage(rows, context)));
    nodes.extend(section(
        if rows.exhaustive {
            "Rows"
        } else {
            "Sampled Rows"
        },
        row_counts(rows, context),
    ));
    nodes.extend(section(
        "Changed Columns",
        changed_columns(model, rows, context),
    ));
    let verbose_examples: Option<Node> =
        if context.text.verbose && !model.unequal_samples.is_empty() {
            examples(model, context, None)
        } else {
            None
        };
    if let Some(content) = verbose_examples {
        nodes.extend(section("Examples", content));
    }
    for (label, samples) in [
        (context.from_label, &model.left_only_keys),
        (context.to_label, &model.right_only_keys),
    ] {
        if !samples.is_empty() {
            nodes.extend(section(
                &format!("{label} only"),
                side_only(label, samples, context.text.max_row_only_examples),
            ));
        }
    }
    nodes
}

fn section(title: &str, content: Node) -> [Node; 4] {
    [
        Node::styled(title, BOLD),
        Node::styled("▔".repeat(title.chars().count()), BOLD),
        content,
        Node::plain(""),
    ]
}

fn overview(model: &DiffModelFacts, mode_label: &str) -> Node {
    let mut table: Table = Table::grid(
        vec![
            column(Justify::Right, OBJECT),
            column(Justify::Left, Style::PLAIN),
        ],
        2,
    );
    let mut add = |label: &str, value: String| {
        table.add_row(vec![Node::plain(label), Node::plain(value)]);
    };
    add(
        if model.input_kind == QUERY_INPUT_KIND {
            "Input"
        } else {
            "Model"
        },
        model.name.clone(),
    );
    add(
        "Key",
        if model.unique_key.is_empty() {
            "<not used>".to_owned()
        } else {
            model.unique_key.join(", ")
        },
    );
    add(
        "Comparison",
        if model.bounded_fallback {
            format!("{mode_label} (fallback to full row diff)")
        } else {
            mode_label.to_owned()
        },
    );
    if model.bounded_fallback {
        add(
            "Fallback",
            "no cursor configured; used full row diff".to_owned(),
        );
    }
    if !model.excluded_columns.is_empty() {
        add("Excluded", model.excluded_columns.join(", "));
    }
    if let Some(rows) = &model.rows {
        add("Scope", row_scope(rows, model.unkeyed));
        if let Some(label) = tolerance_label(&rows.columns) {
            add("Tolerances", label);
        }
    }
    Node::Table(table)
}

fn tolerance_label(columns: &[DiffColumnFacts]) -> Option<String> {
    let labels: Vec<String> = columns
        .iter()
        .filter_map(|column| {
            let (absolute, relative) = column.tolerance.as_ref()?;
            let mut parts: Vec<String> = Vec::new();
            if let Some(value) = absolute {
                parts.push(format!("absolute={value}"));
            }
            if let Some(value) = relative {
                parts.push(format!("relative={value}"));
            }
            Some(format!("{} {}", column.name, parts.join(" ")))
        })
        .collect();
    (!labels.is_empty()).then(|| labels.join(", "))
}

fn row_scope(rows: &DiffRowFacts, unkeyed: bool) -> String {
    if unkeyed {
        return format!(
            "exhaustive ({} multiset rows)",
            grouped(rows.population_count)
        );
    }
    let Some((row_limit, seed)) = rows.sampling else {
        return format!("exhaustive ({} union keys)", grouped(rows.population_count));
    };
    if rows.exhaustive {
        return format!(
            "exhaustive ({} union keys; configured sample limit {})",
            grouped(rows.compared_count),
            grouped(row_limit)
        );
    }
    format!(
        "sampled {} of {} union keys ({}; seed {seed})",
        grouped(rows.compared_count),
        grouped(rows.population_count),
        percentage(rows.compared_count, rows.population_count)
    )
}

fn cursor_extent(rows: &DiffRowFacts, coverage: &DiffCoverageFacts) -> String {
    if rows.cursor_column.is_none() {
        return "<not bounded by cursor>".to_owned();
    }
    let text = |value: &Option<_>, missing: &str| -> String {
        value.as_ref().map_or_else(
            || missing.to_owned(),
            |value: &crate::diff_report::models::DiffValue| value.text.clone(),
        )
    };
    format!(
        "{} to {} (requested {} to {})",
        text(&coverage.minimum_cursor, "<empty>"),
        text(&coverage.maximum_cursor, "<empty>"),
        text(&rows.cursor_start, "unbounded"),
        text(&rows.cursor_end, "unbounded")
    )
}

fn coverage(rows: &DiffRowFacts, context: &SectionContext<'_>) -> Node {
    let (Some(left), Some(right)) = (&rows.left_coverage, &rows.right_coverage) else {
        return Node::styled("Coverage was not collected.", ITALIC);
    };
    let mut table: Table = Table::grid(
        vec![
            column(Justify::Left, OBJECT),
            column(Justify::Right, Style::PLAIN),
            column(Justify::Left, Style::PLAIN),
        ],
        2,
    );
    table.add_row(texts(&[
        "Side".to_owned(),
        "Rows".to_owned(),
        "Cursor extent".to_owned(),
    ]));
    for (label, side) in [(context.from_label, left), (context.to_label, right)] {
        table.add_row(texts(&[
            label.to_owned(),
            grouped(side.row_count),
            cursor_extent(rows, side),
        ]));
    }
    let mut nodes: Vec<Node> = vec![Node::Table(table)];
    if rows.cursor_column.is_some() && rows.coverage_differs {
        nodes.push(Node::plain(""));
        nodes.push(Node::styled(
            "Warning: cursor coverage differs between sides; comparison continued without \
             narrowing the requested bounds.",
            WARNING,
        ));
    }
    Node::Group(nodes)
}

fn schema_summary(model: &DiffModelFacts) -> Node {
    if !has_schema_differences(model) {
        return Node::styled("No schema differences.", ITALIC);
    }
    let count = |items: usize| grouped(items as i64);
    let mut lines: Vec<Node> = vec![Node::plain(format!(
        "schema differences: {}",
        count(model.added_columns.len() + model.removed_columns.len() + model.type_changes.len())
    ))];
    for (label, items) in [
        ("added columns", model.added_columns.len()),
        ("removed columns", model.removed_columns.len()),
        ("type changes", model.type_changes.len()),
    ] {
        if items > 0 {
            lines.push(Node::plain(format!("{label}: {}", count(items))));
        }
    }
    Node::Group(lines)
}

fn delta_label(left: i64, right: i64) -> String {
    if left == 0 {
        return "(no baseline)".to_owned();
    }
    if left == right {
        return "(no change)".to_owned();
    }
    let ratio: f64 = right as f64 / left as f64;
    if right > left {
        format!("(+{})", percent(ratio - 1.0))
    } else {
        format!("(-{})", percent(1.0 - ratio))
    }
}

fn venn_box(rows: &[(Node, bool)]) -> Node {
    let mut table: Table = boxed(
        vec![column(Justify::Left, Style::PLAIN); 5],
        HEAVY_EDGE,
        (0, 0),
    );
    for (cell, section_after) in rows {
        table.add_row(vec![cell.clone(); 5]);
        if *section_after {
            table.add_section();
        }
    }
    Node::Table(table)
}

fn row_counts(rows: &DiffRowFacts, context: &SectionContext<'_>) -> Node {
    let center: Column = column(Justify::Center, Style::PLAIN);
    let mut counts: Table = Table::grid(vec![center.clone(), center.clone(), center], 2);
    counts.add_row(texts(&[
        format!("{} count", context.from_label),
        String::new(),
        format!("{} count", context.to_label),
    ]));
    counts.add_row(texts(&[
        grouped(rows.left_count),
        delta_label(rows.left_count, rows.right_count),
        grouped(rows.right_count),
    ]));
    let joined: i64 = rows.equal_count + rows.unequal_count;
    let blank: Node = Node::plain(" ");
    let mut left_rows: Vec<(Node, bool)> = Vec::new();
    let mut right_rows: Vec<(Node, bool)> = Vec::new();
    if rows.left_only_count > 0 {
        left_rows.push((Node::styled("-", REMOVED), true));
    }
    if rows.equal_count > 0 {
        left_rows.push((blank.clone(), true));
        right_rows.push((blank.clone(), true));
    }
    if rows.unequal_count > 0 {
        left_rows.push((blank.clone(), false));
        right_rows.push((blank, true));
    }
    if rows.right_only_count > 0 {
        right_rows.push((Node::styled("+", ADDED), false));
    }
    let shifted: bool = rows.left_only_count > 0;
    let right_box: Node = venn_box(&right_rows);
    let diagram: Vec<Node> = vec![
        venn_box(&left_rows),
        row_separator(rows),
        if shifted {
            Node::Group(vec![Node::plain("\n"), right_box])
        } else {
            right_box
        },
        row_stats(rows, joined, context),
        joined_annotation(rows, joined),
    ];
    Node::Group(vec![
        Node::Table(counts),
        Node::plain(""),
        Node::Columns(diagram),
        Node::plain(""),
        Node::plain(format!("joined: {}", grouped(joined))),
    ])
}

fn row_separator(rows: &DiffRowFacts) -> Node {
    let mut parts: Vec<Node> = Vec::new();
    if rows.left_only_count > 0 {
        parts.push(Node::plain("\n"));
    }
    for (count, symbol) in [(rows.equal_count, " = "), (rows.unequal_count, " ≠ ")] {
        if count > 0 {
            parts.push(Node::plain("╌╌╌"));
            parts.push(Node::styled(symbol, BOLD));
        }
    }
    parts.push(Node::plain("╌╌╌"));
    Node::Group(parts)
}

fn row_stats(rows: &DiffRowFacts, joined: i64, context: &SectionContext<'_>) -> Node {
    let mut table: Table = boxed(
        vec![
            column(Justify::Right, Style::PLAIN),
            column(Justify::Left, Style::PLAIN),
            column(Justify::Right, Style::PLAIN),
        ],
        ROUNDED,
        (1, 0),
    );
    let entries: [(i64, String, i64); 4] = [
        (
            rows.left_only_count,
            format!("{} only", context.from_label),
            rows.left_count,
        ),
        (rows.equal_count, "equal".to_owned(), joined),
        (rows.unequal_count, "unequal".to_owned(), joined),
        (
            rows.right_only_count,
            format!("{} only", context.to_label),
            rows.right_count,
        ),
    ];
    for (count, label, denominator) in entries {
        table.add_row(texts(&[
            grouped(count),
            label,
            format!("({})", percentage(count, denominator)),
        ]));
        table.add_section();
    }
    Node::Table(table)
}

fn joined_annotation(rows: &DiffRowFacts, joined: i64) -> Node {
    if joined == 0 {
        return Node::plain("");
    }
    let mut lines: Vec<Node> = Vec::new();
    if rows.left_only_count > 0 {
        lines.push(Node::plain("\n"));
    }
    lines.push(Node::plain("╌╮"));
    lines.push(Node::plain(" │"));
    if rows.equal_count > 0 && rows.unequal_count > 0 {
        lines.push(Node::plain(format!("╌├╴  {}  joined", grouped(joined))));
        lines.push(Node::plain(" │"));
    }
    lines.push(Node::plain("╌╯"));
    Node::Group(lines)
}

fn changed_columns(
    model: &DiffModelFacts,
    rows: &DiffRowFacts,
    context: &SectionContext<'_>,
) -> Node {
    let mut mismatched: Vec<&DiffColumnFacts> = rows
        .columns
        .iter()
        .filter(|column| column.mismatched_count > 0)
        .collect();
    mismatched.sort_by(|a, b| {
        b.mismatched_count
            .cmp(&a.mismatched_count)
            .then_with(|| a.name.cmp(&b.name))
    });
    if mismatched.is_empty() {
        return Node::styled(
            if rows.exhaustive {
                "No changed columns."
            } else {
                "No changed columns in sampled keys."
            },
            ITALIC,
        );
    }
    let mut name_column: Column = column(Justify::Left, OBJECT);
    name_column.max_width = Some(CHANGED_COLUMN_NAME_WIDTH);
    let mut table: Table = boxed(
        vec![
            name_column,
            column(Justify::Right, Style::PLAIN),
            column(Justify::Right, Style::PLAIN),
        ],
        SQUARE,
        (1, 1),
    );
    let visible: Vec<&DiffColumnFacts> = mismatched
        .iter()
        .copied()
        .take(TOP_CHANGED_COLUMNS)
        .collect();
    for item in &visible {
        let matching: i64 = (rows.joined_count - item.mismatched_count).max(0);
        table.add_row(texts(&[
            item.name.clone(),
            format!("mismatches={}", grouped(item.mismatched_count)),
            format!("match={}", percentage(matching, rows.joined_count)),
        ]));
    }
    if mismatched.len() > visible.len() {
        table.add_section();
        table.add_row(vec![
            Node::styled("...", MUTED),
            Node::styled(
                format!(
                    "and {} more",
                    grouped((mismatched.len() - visible.len()) as i64)
                ),
                MUTED,
            ),
            Node::styled("", MUTED),
        ]);
    }
    if context.text.verbose {
        return Node::Table(table);
    }
    let names: Vec<String> = visible.iter().map(|item| item.name.clone()).collect();
    match examples(model, context, Some(&names)) {
        Some(content) => Node::Group(vec![
            Node::Table(table),
            Node::plain(""),
            content,
            Node::plain(""),
            Node::styled("Use --verbose to show more example row changes.", MUTED),
        ]),
        None => Node::Table(table),
    }
}

fn key_label(values: &[DiffNamedValue], separator: &str) -> String {
    values
        .iter()
        .map(|(name, value)| format!("{name}={}", render_key_value(&value.text)))
        .collect::<Vec<String>>()
        .join(separator)
}

fn examples(
    model: &DiffModelFacts,
    context: &SectionContext<'_>,
    visible: Option<&[String]>,
) -> Option<Node> {
    let mut grouped_examples: BTreeMap<&str, Vec<String>> = BTreeMap::new();
    for sample in &model.unequal_samples {
        let key: String = key_label(&sample.key_values, ", ");
        for cell in &sample.changed_cells {
            let (left, right) =
                render_example_pair(&cell.left.text, &cell.right.text, context.examples);
            let difference: String = match left.first_difference {
                Some(index) if left.truncated || right.truncated => {
                    format!(
                        " (first difference at character {})",
                        grouped(index as i64 + 1)
                    )
                }
                _ => String::new(),
            };
            grouped_examples
                .entry(cell.name.as_str())
                .or_default()
                .push(format!(
                    "{key} | {} -> {}{difference}",
                    display_example_value(&left),
                    display_example_value(&right)
                ));
        }
    }
    let limit: usize = context.text.max_column_examples;
    let mut blocks: Vec<Node> = Vec::new();
    for (name, all) in grouped_examples {
        if visible.is_some_and(|names| !names.iter().any(|visible| visible == name)) {
            continue;
        }
        blocks.push(Node::styled(name, OBJECT));
        for example in all.iter().take(limit) {
            blocks.push(Node::plain(format!("  - {example}")));
        }
        if all.len() > limit {
            blocks.push(Node::styled(
                format!(
                    "  showing {} of {} examples",
                    grouped(limit as i64),
                    grouped(all.len() as i64)
                ),
                MUTED,
            ));
        }
        blocks.push(Node::plain(""));
    }
    blocks.pop().map(|_| Node::Group(blocks))
}

fn side_only(label: &str, samples: &[Vec<DiffNamedValue>], limit: usize) -> Node {
    let mut blocks: Vec<Node> = samples
        .iter()
        .take(limit)
        .map(|sample| Node::plain(format!("  - {}", key_label(sample, " | "))))
        .collect();
    if samples.len() > limit {
        blocks.push(Node::styled(
            format!(
                "  showing {} of {} {label} only rows",
                grouped(limit as i64),
                grouped(samples.len() as i64)
            ),
            MUTED,
        ));
    }
    if blocks.is_empty() {
        return Node::styled("No side-only samples collected.", ITALIC);
    }
    Node::Group(blocks)
}
