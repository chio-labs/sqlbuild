//! Rows of queued input, built on the delivery thread so producers only enqueue.

use std::collections::HashSet;

use crate::records::constants::{
    ARTIFACT_DIGEST_PREFIX, EXECUTED_SQL_ROLE, SQL_ARTIFACT_KIND, SQL_MEDIA_TYPE,
};
use crate::records::main::artifact_rows::artifact_rows;
use crate::records::main::event_object_row::event_object_row;
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::sha256_hex::sha256_hex;
use crate::records::models::{ArtifactInput, RecallRow, RowEnvelope};
use crate::writer::_helpers::queue::{Payload, Queued, SqlInput};
use crate::writer::models::DeliveryStream;

/// A batch ready to write: its rows, the streams of the records they came from, and records already settled.
#[derive(Debug, Default)]
pub(crate) struct Built {
    pub(crate) rows: Vec<RecallRow>,
    /// One entry per record the rows were built from, for delivery accounting.
    pub(crate) written: Vec<DeliveryStream>,
    /// Records that are already stored, such as SQL this invocation recorded before.
    pub(crate) settled: Vec<DeliveryStream>,
    /// Records whose rows could not be built.
    pub(crate) unbuildable: Vec<DeliveryStream>,
}

/// Builds rows for one session; remembers which SQL it has stored.
#[derive(Debug)]
pub(crate) struct Materializer {
    envelope: RowEnvelope,
    artifacts_seen: HashSet<String>,
}

impl Materializer {
    pub(crate) fn new(envelope: RowEnvelope) -> Self {
        Self {
            envelope,
            artifacts_seen: HashSet::new(),
        }
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

    /// The rows of `batch`, with each record's stream sorted by how it is accounted.
    pub(crate) fn build(&mut self, batch: Vec<Queued>) -> Built {
        let mut built = Built::default();
        for record in batch {
            let stream: DeliveryStream = record.stream;
            match record.payload {
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
                Payload::Sql(input) => match self.sql_rows(input) {
                    Some(rows) => {
                        built.rows.extend(rows);
                        built.written.push(stream);
                    }
                    None => built.settled.push(stream),
                },
            }
        }
        built
    }
}
