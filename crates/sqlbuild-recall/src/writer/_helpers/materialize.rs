//! Rows of queued input, built on the delivery thread so producers only enqueue.

use std::collections::HashSet;

use crate::records::constants::{
    ARTIFACT_DIGEST_PREFIX, EXECUTED_SQL_ROLE, SQL_ARTIFACT_KIND, SQL_MEDIA_TYPE,
};
use crate::records::main::artifact_rows::artifact_rows;
use crate::records::main::event_object_row::event_object_row;
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::output_row::output_row;
use crate::records::main::sha256_hex::sha256_hex;
use crate::records::models::{ArtifactInput, OutputChunk, OutputStream, RecallRow, RowEnvelope};
use crate::writer::_helpers::output_chunk::output_chunk;
use crate::writer::_helpers::queue::{Payload, Queued, SqlInput};
use crate::writer::models::{DeliveryStream, ReplacedEvents, ReplacedOutput};
use crate::writer::types::{OutputReplacement, PendingLifecycleEvent};

/// A batch ready to write: its rows, the streams of the records they came from, and records already settled.
#[derive(Debug, Default)]
pub(crate) struct Built {
    pub(crate) rows: Vec<RecallRow>,
    /// One entry per record the rows were built from, for delivery accounting.
    pub(crate) written: Vec<DeliveryStream>,
    /// Records that are already stored, such as SQL this invocation recorded before.
    pub(crate) settled: Vec<DeliveryStream>,
    /// Records whose rows could not be built, or that a replacement sink failed on.
    pub(crate) unbuildable: Vec<DeliveryStream>,
    /// Records a replacement sink chose not to store.
    pub(crate) filtered: Vec<DeliveryStream>,
    /// Events a lifecycle replacement published beyond the one it was handed, accepted as they are built.
    pub(crate) extra_events: u64,
}

/// Builds rows for one session; remembers which SQL it has stored.
#[derive(Debug)]
pub(crate) struct Materializer {
    envelope: RowEnvelope,
    artifacts_seen: HashSet<String>,
    /// Output bytes stored per stream, for the offsets of replaced chunks.
    output_bytes: [u64; 2],
}

impl Materializer {
    pub(crate) fn new(envelope: RowEnvelope) -> Self {
        Self {
            envelope,
            artifacts_seen: HashSet::new(),
            output_bytes: [0; 2],
        }
    }

    /// The output rows to store for `rows`, passed through `replacement`: what it published, under the chunk's sequence.
    fn output_rows(
        &mut self,
        rows: Vec<RecallRow>,
        replacement: Option<&dyn OutputReplacement>,
    ) -> Result<Vec<RecallRow>, ReplacedOutput> {
        let mut stored: Vec<RecallRow> = Vec::with_capacity(rows.len());
        for row in rows {
            let Some(chunk) = output_chunk(&row) else {
                stored.push(row);
                continue;
            };
            let index = usize::from(chunk.stream == OutputStream::Stderr);
            let Some(replacement) = replacement else {
                self.output_bytes[index] += chunk.data.len() as u64;
                stored.push(row);
                continue;
            };
            if chunk.omitted.is_some() {
                let gap = OutputChunk {
                    byte_offset: self.output_bytes[index],
                    ..chunk
                };
                stored.push(output_row(&self.envelope, &gap));
                continue;
            }
            match replacement.replace(&chunk) {
                ReplacedOutput::Published(data) => {
                    let replaced = OutputChunk {
                        byte_offset: self.output_bytes[index],
                        data,
                        ..chunk
                    };
                    self.output_bytes[index] += replaced.data.len() as u64;
                    stored.push(output_row(&self.envelope, &replaced));
                }
                other => return Err(other),
            }
        }
        Ok(stored)
    }

    fn sql_rows(&mut self, input: SqlInput) -> Option<Vec<RecallRow>> {
        let digest = format!(
            "{ARTIFACT_DIGEST_PREFIX}{}",
            sha256_hex(input.sql.as_bytes())
        );
        if !self.artifacts_seen.insert(digest.clone()) {
            return None;
        }
        let artifact = ArtifactInput {
            ref_id: input.statement_id.clone().unwrap_or_else(|| digest.clone()),
            digest,
            kind: SQL_ARTIFACT_KIND.to_owned(),
            media_type: SQL_MEDIA_TYPE.to_owned(),
            content: input.sql.into_bytes(),
            seen_at: format_timestamp(input.seen_at),
            role: EXECUTED_SQL_ROLE.to_owned(),
            statement_id: input.statement_id,
            resource_id: input.resource_id,
        };
        Some(artifact_rows(&self.envelope, &artifact).to_vec())
    }

    /// The rows of `batch`, with each record's stream sorted by how it is accounted; lifecycle replacements see their events in publication order.
    pub(crate) fn build(
        &mut self,
        batch: Vec<Queued>,
        replacement: Option<&dyn OutputReplacement>,
    ) -> Built {
        let mut built = Built::default();
        let mut pending_events: Vec<(u64, Box<dyn PendingLifecycleEvent>)> = Vec::new();
        for record in batch {
            let stream: DeliveryStream = record.stream;
            match record.payload {
                Payload::Rows(rows) if stream == DeliveryStream::Output => {
                    match self.output_rows(rows, replacement) {
                        Ok(rows) => {
                            built.rows.extend(rows);
                            built.written.push(stream);
                        }
                        Err(ReplacedOutput::Filtered) => built.filtered.push(stream),
                        Err(_) => built.unbuildable.push(stream),
                    }
                }
                Payload::Rows(rows) => {
                    built.rows.extend(rows);
                    built.written.push(stream);
                }
                Payload::Event(event) => match event_object_row(&self.envelope, &event) {
                    Ok(row) => {
                        built.rows.push(row);
                        built.written.push(stream);
                    }
                    Err(_) => built.unbuildable.push(stream),
                },
                Payload::Pending(sequence, pending) => pending_events.push((sequence, pending)),
                Payload::Sql(input) => match self.sql_rows(input) {
                    Some(rows) => {
                        built.rows.extend(rows);
                        built.written.push(stream);
                    }
                    None => built.settled.push(stream),
                },
            }
        }
        pending_events.sort_by_key(|(sequence, _)| *sequence);
        for (_, pending) in pending_events {
            let stream = DeliveryStream::Events;
            match pending.replace() {
                ReplacedEvents::Published(events) if events.is_empty() => {
                    built.filtered.push(stream);
                }
                ReplacedEvents::Published(events) => {
                    built.extra_events += events.len() as u64 - 1;
                    for event in events {
                        match event_object_row(&self.envelope, &event) {
                            Ok(row) => {
                                built.rows.push(row);
                                built.written.push(stream);
                            }
                            Err(_) => built.unbuildable.push(stream),
                        }
                    }
                }
                ReplacedEvents::Failed => built.unbuildable.push(stream),
            }
        }
        built
    }
}
