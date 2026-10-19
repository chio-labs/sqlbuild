//! `read_output_transcript`: one invocation's exact output bytes and their completeness.

use rusqlite::OptionalExtension;

use crate::records::models::OutputStream;
use crate::store::_helpers::sqlite::checked;
use crate::store::_helpers::truncation::with_truncation_notes;
use crate::store::errors::StoreError;
use crate::store::models::{OutputTranscript, SqliteStore, StoredChunk};

/// The bytes of `stream`, or both streams interleaved by sequence when `None`.
pub fn read_output_transcript(
    store: &SqliteStore,
    invocation_id: &str,
    stream: Option<OutputStream>,
) -> Result<OutputTranscript, StoreError> {
    let mut statement = checked(
        store.connection.prepare(
            "SELECT stream, data, omitted_bytes FROM recall_output WHERE invocation_id = ?1 \
             AND (?2 IS NULL OR stream = ?2) ORDER BY sequence",
        ),
        "read Recall output",
    )?;
    let chunks: Vec<StoredChunk> = checked(
        statement
            .query_map(
                rusqlite::params![invocation_id, stream.map(OutputStream::as_str)],
                |row| {
                    Ok(StoredChunk {
                        stream: row.get(0)?,
                        data: row.get(1)?,
                        omitted_bytes: row.get(2)?,
                    })
                },
            )
            .and_then(Iterator::collect),
        "read Recall output",
    )?;
    let mut transcript = OutputTranscript {
        invocation_id: invocation_id.to_owned(),
        data: with_truncation_notes(&chunks),
        ..OutputTranscript::default()
    };
    transcript.status = checked(
        store
            .connection
            .query_row(
                "SELECT status FROM invocations WHERE invocation_id = ?1",
                [invocation_id],
                |row| row.get(0),
            )
            .optional(),
        "read Recall invocation",
    )?;
    let completeness: Option<(i64, i64, i64, bool, bool, Option<String>)> = checked(
        store
            .connection
            .query_row(
                "SELECT missing_sequences, reported_drops, filtered, flush_complete, complete, \
                 gap_reason FROM output_invocations WHERE invocation_id = ?1",
                [invocation_id],
                |row| {
                    Ok((
                        row.get(0)?,
                        row.get(1)?,
                        row.get(2)?,
                        row.get(3)?,
                        row.get(4)?,
                        row.get(5)?,
                    ))
                },
            )
            .optional(),
        "read Recall output completeness",
    )?;
    if let Some((missing, drops, filtered, flushed, complete, reason)) = completeness {
        transcript.missing_sequences = missing;
        transcript.reported_drops = drops;
        transcript.filtered = filtered;
        transcript.flush_complete = flushed;
        transcript.complete = complete;
        transcript.gap_reason = reason;
    }
    Ok(transcript)
}
