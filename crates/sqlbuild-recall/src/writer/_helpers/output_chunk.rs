//! The output chunk a queued `recall_output` row was built from.

use crate::records::constants::{
    DROPPED_BEFORE_COLUMN, OMITTED_BYTES_COLUMN, OMITTED_SEQUENCES_COLUMN,
};
use crate::records::models::{OmittedOutput, OutputChunk, OutputStream, RecallRow, RecallValue};
use crate::schema::models::Table;

fn count(row: &RecallRow, column: &str) -> Option<u64> {
    match row.value(column)? {
        RecallValue::Integer(number) if *number >= 0 => Some(number.unsigned_abs()),
        _ => None,
    }
}

fn text<'a>(row: &'a RecallRow, column: &str) -> Option<&'a str> {
    match row.value(column)? {
        RecallValue::Text(text) => Some(text),
        _ => None,
    }
}

/// The chunk `row` stores, `None` for a row of another table.
pub(crate) fn output_chunk(row: &RecallRow) -> Option<OutputChunk> {
    if row.table != Table::Output {
        return None;
    }
    let data: Vec<u8> = match row.value("data")? {
        RecallValue::Blob(data) => data.clone(),
        RecallValue::Text(text) => text.as_bytes().to_vec(),
        _ => return None,
    };
    Some(OutputChunk {
        sequence: count(row, "sequence")?,
        stream: OutputStream::from_name(text(row, "stream")?)?,
        occurred_at: text(row, "occurred_at")?.to_owned(),
        data,
        byte_offset: count(row, "byte_offset")?,
        dropped_before: count(row, DROPPED_BEFORE_COLUMN)?,
        omitted: count(row, OMITTED_BYTES_COLUMN).map(|bytes| OmittedOutput {
            bytes,
            sequences: count(row, OMITTED_SEQUENCES_COLUMN).unwrap_or(1),
        }),
    })
}
