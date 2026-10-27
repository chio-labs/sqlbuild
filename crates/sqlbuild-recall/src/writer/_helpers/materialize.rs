//! Rows of queued input, built on the delivery thread so producers only enqueue.

use std::collections::HashSet;

use serde_json::{Map, Value};

use crate::records::constants::{
    ARTIFACT_DIGEST_PREFIX, AUDIT_COMPLETED_EVENT, AUDIT_EVIDENCE_KIND, AUDIT_EVIDENCE_MEDIA_TYPE,
    AUDIT_EVIDENCE_ROLE, EVIDENCE_PAYLOAD_FIELD, EXECUTED_SQL_ROLE, SAMPLE_DIGEST_PAYLOAD_FIELD,
    SQL_ARTIFACT_KIND, SQL_MEDIA_TYPE,
};
use crate::records::main::artifact_rows::artifact_rows;
use crate::records::main::event_object_row::event_object_row;
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::output_row::output_row;
use crate::records::main::sha256_hex::sha256_hex;
use crate::records::models::{ArtifactInput, OutputChunk, OutputStream, RecallRow, RowEnvelope};
use crate::settings::models::AuditEvidence;
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
    /// Audit evidence artifacts taken out of their events, accepted as they are built.
    pub(crate) extra_artifacts: u64,
}

/// Builds rows for one session; remembers which SQL and references it has stored.
#[derive(Debug)]
pub(crate) struct Materializer {
    envelope: RowEnvelope,
    artifacts_seen: HashSet<String>,
    /// Digests and the references already written for them.
    refs_seen: HashSet<(String, String)>,
    /// Output bytes stored per stream, for the offsets of replaced chunks.
    output_bytes: [u64; 2],
    audit_evidence: AuditEvidence,
}

impl Materializer {
    pub(crate) fn new(envelope: RowEnvelope, audit_evidence: AuditEvidence) -> Self {
        Self {
            audit_evidence,
            envelope,
            artifacts_seen: HashSet::new(),
            refs_seen: HashSet::new(),
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

    /// The content row the first time a digest is seen, and a reference row for each statement that ran it; `None` when both are already written.
    fn sql_rows(&mut self, input: SqlInput) -> Option<Vec<RecallRow>> {
        let artifact: ArtifactInput = artifact_input(
            input.sql.into_bytes(),
            (SQL_ARTIFACT_KIND, SQL_MEDIA_TYPE, EXECUTED_SQL_ROLE),
            (input.statement_id, input.resource_id),
            &format_timestamp(input.seen_at),
        );
        self.artifact_rows(artifact)
    }

    /// `artifact`'s content row the first time its digest is seen and its reference row the first time it is named; `None` when both are written.
    fn artifact_rows(&mut self, artifact: ArtifactInput) -> Option<Vec<RecallRow>> {
        if !self
            .refs_seen
            .insert((artifact.digest.clone(), artifact.ref_id.clone()))
        {
            return None;
        }
        let first_sighting: bool = self.artifacts_seen.insert(artifact.digest.clone());
        let [content, reference] = artifact_rows(&self.envelope, &artifact);
        Some(if first_sighting {
            vec![content, reference]
        } else {
            vec![reference]
        })
    }

    /// The row of `event`; an `audit_completed` event's evidence rows leave its payload and, when the outcome keeps them, become an artifact its `sample_digest` names.
    fn event_rows(
        &mut self,
        mut event: Map<String, Value>,
        built: &mut Built,
    ) -> Result<RecallRow, crate::records::errors::RecordError> {
        if let Some(artifact) = self.take_evidence(&mut event)
            && let Some(rows) = self.artifact_rows(artifact)
        {
            built.rows.extend(rows);
            built.written.push(DeliveryStream::Artifacts);
            built.extra_artifacts += 1;
        }
        event_object_row(&self.envelope, &event)
    }

    fn take_evidence(&self, event: &mut Map<String, Value>) -> Option<ArtifactInput> {
        if event.get("event_type").and_then(Value::as_str) != Some(AUDIT_COMPLETED_EVENT) {
            return None;
        }
        let resource_id: Option<String> = event
            .get("resource_id")
            .and_then(Value::as_str)
            .map(str::to_owned);
        let event_id: String = event
            .get("event_id")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let seen_at: String = event
            .get("occurred_at")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let payload: &mut Map<String, Value> = event.get_mut("payload")?.as_object_mut()?;
        let evidence: Value = payload.remove(EVIDENCE_PAYLOAD_FIELD)?;
        let outcome: &str = payload
            .get("outcome")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if !self.audit_evidence.keeps(outcome) {
            return None;
        }
        let content: Vec<u8> = serde_json::to_vec(&evidence).ok()?;
        let mut artifact: ArtifactInput = artifact_input(
            content,
            (
                AUDIT_EVIDENCE_KIND,
                AUDIT_EVIDENCE_MEDIA_TYPE,
                AUDIT_EVIDENCE_ROLE,
            ),
            (None, resource_id),
            &seen_at,
        );
        artifact.ref_id = event_id;
        let digest: &str = artifact
            .digest
            .strip_prefix(ARTIFACT_DIGEST_PREFIX)
            .unwrap_or(&artifact.digest);
        payload.insert(
            SAMPLE_DIGEST_PAYLOAD_FIELD.to_owned(),
            Value::from(digest.to_owned()),
        );
        Some(artifact)
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
                Payload::Event(event) => match self.event_rows(event, &mut built) {
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
                        match self.event_rows(event, &mut built) {
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

/// An artifact of `content`, referenced by its statement or, without one, by its digest.
fn artifact_input(
    content: Vec<u8>,
    (kind, media_type, role): (&str, &str, &str),
    (statement_id, resource_id): (Option<String>, Option<String>),
    seen_at: &str,
) -> ArtifactInput {
    let digest = format!("{ARTIFACT_DIGEST_PREFIX}{}", sha256_hex(&content));
    ArtifactInput {
        ref_id: statement_id.clone().unwrap_or_else(|| digest.clone()),
        digest,
        kind: kind.to_owned(),
        media_type: media_type.to_owned(),
        content,
        seen_at: seen_at.to_owned(),
        role: role.to_owned(),
        statement_id,
        resource_id,
    }
}
