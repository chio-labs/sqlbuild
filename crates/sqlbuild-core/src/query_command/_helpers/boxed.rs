//! Query rows in a box: names and types centered over aligned columns.

use crate::query_command::constants::{
    BOX_BOTTOM, BOX_HORIZONTAL, BOX_RULE, BOX_TOP, BOX_VERTICAL,
};
use crate::query_command::models::QueryDisplay;
use crate::text::main::cell_len::cell_len;

/// Whether `value` prints on one line, so a box can hold it.
fn single_line(value: &str) -> bool {
    !value.chars().any(char::is_control)
}

fn rule(widths: &[usize], [left, middle, right]: [char; 3]) -> String {
    let segments: Vec<String> = widths
        .iter()
        .map(|width| BOX_HORIZONTAL.to_string().repeat(width + 2))
        .collect();
    format!("{left}{}{right}", segments.join(&middle.to_string()))
}

fn centered(text: &str, width: usize) -> String {
    let spare: usize = width.saturating_sub(cell_len(text));
    let left: usize = spare / 2;
    format!("{}{text}{}", " ".repeat(left), " ".repeat(spare - left))
}

fn aligned(text: &str, width: usize, right: bool) -> String {
    let spare: String = " ".repeat(width.saturating_sub(cell_len(text)));
    if right {
        format!("{spare}{text}")
    } else {
        format!("{text}{spare}")
    }
}

fn line(cells: Vec<String>) -> String {
    let joined: String = cells.join(&format!(" {BOX_VERTICAL} "));
    format!("{BOX_VERTICAL} {joined} {BOX_VERTICAL}")
}

/// The box's lines when it is at most `limit` cells wide and every value is one line; `None` otherwise, so nothing is cut to fit.
pub(crate) fn boxed_lines(display: &QueryDisplay, limit: usize) -> Option<Vec<String>> {
    let types: Vec<&str> = (0..display.columns.len())
        .map(|index| {
            display
                .types
                .get(index)
                .and_then(Option::as_deref)
                .unwrap_or_default()
        })
        .collect();
    let mut widths: Vec<usize> = display
        .columns
        .iter()
        .zip(&types)
        .map(|(column, kind)| cell_len(column).max(cell_len(kind)))
        .collect();
    for row in &display.rows {
        for (index, value) in row.iter().enumerate() {
            if !single_line(value) {
                return None;
            }
            if let Some(width) = widths.get_mut(index) {
                *width = (*width).max(cell_len(value));
            }
        }
    }
    let total: usize = widths.iter().map(|width| width + 3).sum::<usize>() + 1;
    if total > limit || display.columns.iter().any(|column| !single_line(column)) {
        return None;
    }
    let mut lines: Vec<String> = vec![
        rule(&widths, BOX_TOP),
        line(
            display
                .columns
                .iter()
                .zip(&widths)
                .map(|(column, width)| centered(column, *width))
                .collect(),
        ),
    ];
    if types.iter().any(|kind| !kind.is_empty()) {
        lines.push(line(
            types
                .iter()
                .zip(&widths)
                .map(|(kind, width)| centered(kind, *width))
                .collect(),
        ));
    }
    lines.push(rule(&widths, BOX_RULE));
    for row in &display.rows {
        lines.push(line(
            widths
                .iter()
                .enumerate()
                .map(|(index, width)| {
                    let value: &str = row.get(index).map_or("", String::as_str);
                    let right: bool = display.numeric.get(index).copied().unwrap_or(false);
                    aligned(value, *width, right)
                })
                .collect(),
        ));
    }
    lines.push(rule(&widths, BOX_BOTTOM));
    Some(lines)
}
