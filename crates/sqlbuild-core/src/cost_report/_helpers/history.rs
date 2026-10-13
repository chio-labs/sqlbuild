//! The unstyled rows of the cost history table.

use crate::cost_report::_helpers::decimal_text::fixed;
use crate::cost_report::_helpers::instants::utc_text;
use crate::cost_report::_helpers::tables::{column_widths, padded, usd};
use crate::cost_report::constants::{
    COLUMN_GAP, CREDIT_PLACES, HISTORY_HEADINGS, HISTORY_NUMERIC_COLUMNS,
};
use crate::cost_report::models::CostRun;

fn history_row(run: &CostRun) -> Vec<String> {
    vec![
        utc_text(&run.completed_at).unwrap_or_else(|| run.completed_at.clone()),
        run.run_id.clone(),
        run.build_status.clone(),
        run.cost.status.clone(),
        fixed(&run.cost.estimated_compute_credits, CREDIT_PLACES),
        usd(&run.cost.estimated_usd),
    ]
}

fn aligned(row: &[String], widths: &[usize]) -> String {
    let cells: Vec<String> = row
        .iter()
        .enumerate()
        .map(|(index, value)| {
            padded(
                value,
                widths[index],
                HISTORY_NUMERIC_COLUMNS.contains(&index),
            )
        })
        .collect();
    cells.join(COLUMN_GAP)
}

/// The heading line and one line per run.
pub(crate) fn history_rows(runs: &[CostRun]) -> Vec<String> {
    let rows: Vec<Vec<String>> = runs.iter().map(history_row).collect();
    let widths: Vec<usize> = column_widths(&HISTORY_HEADINGS, &rows);
    let headings: Vec<String> = HISTORY_HEADINGS
        .iter()
        .enumerate()
        .map(|(index, heading)| padded(heading, widths[index], false))
        .collect();
    let mut lines: Vec<String> = vec![headings.join(COLUMN_GAP)];
    lines.extend(rows.iter().map(|row| aligned(row, &widths)));
    lines
}
