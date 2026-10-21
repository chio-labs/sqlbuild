//! The permanent line of one completed microbatch, for output without a live spinner.

use crate::build_progress::models::BatchProgressText;

/// The model, batch position, cursor window, rows written and elapsed time of a batch.
#[must_use]
pub fn batch_progress_message(batch: &BatchProgressText) -> String {
    let rows: String = batch
        .rows_affected
        .map(|rows| format!("  {rows} rows"))
        .unwrap_or_default();
    format!(
        "Batch  {}  {}/{}  {}{rows}  {:.1}s",
        batch.model_name,
        batch.batch_number,
        batch.batch_count,
        batch.window,
        batch.elapsed_seconds
    )
}
