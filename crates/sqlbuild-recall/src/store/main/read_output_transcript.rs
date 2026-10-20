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
    checked(
        store
            .connection
            .query_row(
                "SELECT missing_sequences, reported_drops, filtered, flush_complete, complete, \
                 gap_reason FROM output_invocations WHERE invocation_id = ?1",
                [invocation_id],
                |row| {
                    transcript.missing_sequences = row.get(0)?;
                    transcript.reported_drops = row.get(1)?;
                    transcript.filtered = row.get(2)?;
                    transcript.flush_complete = row.get(3)?;
                    transcript.complete = row.get(4)?;
                    transcript.gap_reason = row.get(5)?;
                    Ok(())
                },
            )
            .optional(),
        "read Recall output completeness",
    )?;
    Ok(transcript)
}
