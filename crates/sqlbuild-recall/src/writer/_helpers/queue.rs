//! The bounded priority queue and the output coalescer, guarded together by one mutex.

use std::collections::VecDeque;
use std::time::{Duration, Instant, SystemTime};

use serde_json::{Map, Value};

use crate::records::constants::{DROPPED_BEFORE_COLUMN, MAX_OUTPUT_CHUNK_BYTES};
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::output_row::output_row;
use crate::records::models::{
    DeliveryCounts, OutputChunk, OutputStream, RecallRow, RecallValue, RowEnvelope,
};
use crate::store::models::InsertOutcome;
use crate::writer::_helpers::delivery::stream_of;
use crate::writer::constants::{QUEUE_BYTE_CAPACITY, QUEUE_RECORD_CAPACITY};
use crate::writer::models::{DeliveryStream, Priority};

/// SQL a statement executed, hashed and turned into rows on the delivery thread.
#[derive(Debug)]
pub(crate) struct SqlInput {
    pub(crate) sql: String,
    pub(crate) statement_id: Option<String>,
    pub(crate) resource_id: Option<String>,
    pub(crate) seen_at: SystemTime,
}

/// What a queued record holds: finished rows, or input the delivery thread turns into rows.
#[derive(Debug)]
pub(crate) enum Payload {
    Rows(Vec<RecallRow>),
    Event(Map<String, Value>),
    Sql(SqlInput),
}

/// One queued record: what is written together and where it is accounted.
#[derive(Debug)]
pub(crate) struct Queued {
    pub(crate) payload: Payload,
    pub(crate) stream: DeliveryStream,
    pub(crate) bytes: usize,
}

impl Queued {
    /// The finished rows; empty while the delivery thread has yet to build them.
    pub(crate) fn rows(&self) -> &[RecallRow] {
        match &self.payload {
            Payload::Rows(rows) => rows,
            Payload::Event(_) | Payload::Sql(_) => &[],
        }
    }

    fn row_count(&self) -> usize {
        match &self.payload {
            Payload::Rows(rows) => rows.len(),
            Payload::Event(_) => 1,
            Payload::Sql(_) => 2,
        }
    }
}

/// Output accepted but not yet chunked: contiguous writes to one stream.
#[derive(Debug)]
struct Pending {
    stream: OutputStream,
    data: Vec<u8>,
    since: Instant,
    occurred_at: String,
}

/// Everything producers and the delivery thread share.
#[derive(Debug)]
pub(crate) struct WriterState {
    pub(crate) envelope: RowEnvelope,
    buckets: [VecDeque<Queued>; Priority::COUNT],
    records: usize,
    bytes: usize,
    pub(crate) counts: [DeliveryCounts; 5],
    pending: Option<Pending>,
    next_sequence: u64,
    offsets: [u64; 2],
    unreported_output_drops: u64,
    pub(crate) diagnostic_sequence: u64,
    pub(crate) closing: bool,
    pub(crate) deadline: Option<Instant>,
    pub(crate) finished: bool,
    pub(crate) rejecting: bool,
    pub(crate) degraded: Option<String>,
    /// Store notices the user should see, such as a corrupt store moved aside.
    pub(crate) notices: Vec<String>,
    capacity: (usize, usize),
}

fn row_bytes(rows: &[RecallRow]) -> usize {
    rows.iter()
        .flat_map(|row| row.values.iter())
        .map(|(name, value)| {
            name.len()
                + match value {
                    RecallValue::Text(text) => text.len(),
                    RecallValue::Blob(data) => data.len(),
                    _ => 8,
                }
        })
        .sum()
}

impl WriterState {
    pub(crate) fn new(envelope: RowEnvelope) -> Self {
        Self::with_capacity(envelope, (QUEUE_RECORD_CAPACITY, QUEUE_BYTE_CAPACITY))
    }

    pub(crate) fn with_capacity(envelope: RowEnvelope, capacity: (usize, usize)) -> Self {
        Self {
            envelope,
            buckets: Default::default(),
            records: 0,
            bytes: 0,
            counts: [DeliveryCounts::default(); 5],
            pending: None,
            next_sequence: 0,
            offsets: [0; 2],
            unreported_output_drops: 0,
            diagnostic_sequence: 0,
            closing: false,
            deadline: None,
            finished: false,
            rejecting: false,
            degraded: None,
            notices: Vec::new(),
            capacity,
        }
    }

    pub(crate) fn counts_mut(&mut self, stream: DeliveryStream) -> &mut DeliveryCounts {
        &mut self.counts[stream.index()]
    }

    /// Count `record` as dropped; a dropped output chunk hands its own earlier drops to the next chunk, so each drop is reported exactly once.
    fn drop_record(&mut self, record: &Queued) {
        self.counts_mut(record.stream).dropped += 1;
        if record.stream == DeliveryStream::Output {
            let carried: u64 = record
                .rows()
                .iter()
                .map(|row| match row.value(DROPPED_BEFORE_COLUMN) {
                    Some(RecallValue::Integer(count)) => u64::try_from(*count).unwrap_or_default(),
                    _ => 0,
                })
                .sum();
            self.unreported_output_drops += 1 + carried;
        }
    }

    fn full(&self, bytes: usize) -> bool {
        self.records >= self.capacity.0 || self.bytes + bytes > self.capacity.1
    }

    /// Queue `rows`, displacing lower-priority records when full; counts acceptance and drops.
    pub(crate) fn push(
        &mut self,
        rows: Vec<RecallRow>,
        stream: DeliveryStream,
        priority: Priority,
    ) {
        let bytes: usize = row_bytes(&rows);
        self.push_record(
            Queued {
                payload: Payload::Rows(rows),
                stream,
                bytes,
            },
            priority,
        );
    }

    /// Queue one record of any payload, displacing lower-priority records when full.
    pub(crate) fn push_record(&mut self, record: Queued, priority: Priority) {
        self.counts_mut(record.stream).accepted += 1;
        if self.rejecting {
            self.drop_record(&record);
            return;
        }
        while self.full(record.bytes) {
            let Some(lowest) = self
                .buckets
                .iter()
                .position(|bucket| !bucket.is_empty())
                .filter(|lowest| *lowest < priority as usize)
            else {
                self.drop_record(&record);
                return;
            };
            if let Some(displaced) = self.buckets[lowest].pop_front() {
                self.records -= 1;
                self.bytes -= displaced.bytes;
                self.drop_record(&displaced);
            }
        }
        self.records += 1;
        self.bytes += record.bytes;
        self.buckets[priority as usize].push_back(record);
    }

    pub(crate) fn queued(&self) -> usize {
        self.records
    }

    /// Up to `limit` rows, highest priority first.
    pub(crate) fn take_batch(&mut self, limit: usize) -> Vec<Queued> {
        let mut batch: Vec<Queued> = Vec::new();
        let mut rows = 0;
        for bucket in self.buckets.iter_mut().rev() {
            while rows < limit {
                let Some(record) = bucket.pop_front() else {
                    break;
                };
                rows += record.row_count();
                self.records -= 1;
                self.bytes -= record.bytes;
                batch.push(record);
            }
        }
        batch
    }

    /// Drop everything queued, as when the store is unusable or the flush budget is spent.
    pub(crate) fn drop_all(&mut self) {
        let records: Vec<Queued> = self.buckets.iter_mut().flat_map(std::mem::take).collect();
        for record in &records {
            self.drop_record(record);
        }
        self.records = 0;
        self.bytes = 0;
    }

    fn emit(&mut self, stream: OutputStream, data: Vec<u8>, occurred_at: &str) {
        let index = usize::from(stream == OutputStream::Stderr);
        let chunk = OutputChunk {
            sequence: self.next_sequence,
            stream,
            occurred_at: occurred_at.to_owned(),
            byte_offset: self.offsets[index],
            dropped_before: std::mem::take(&mut self.unreported_output_drops),
            data,
        };
        self.next_sequence += 1;
        self.offsets[index] += chunk.data.len() as u64;
        let row = output_row(&self.envelope, &chunk);
        self.push(vec![row], DeliveryStream::Output, Priority::Output);
    }

    /// Accept `data` written to `stream`: a stream switch flushes the other stream first, so the shared sequence preserves interleaving; full chunks are emitted at once.
    pub(crate) fn append_output(&mut self, stream: OutputStream, data: &[u8], now: SystemTime) {
        if data.is_empty() {
            return;
        }
        if self
            .pending
            .as_ref()
            .is_some_and(|pending| pending.stream != stream)
        {
            self.flush_output();
        }
        let pending = self.pending.get_or_insert_with(|| Pending {
            stream,
            data: Vec::new(),
            since: Instant::now(),
            occurred_at: format_timestamp(now),
        });
        pending.data.extend_from_slice(data);
        while self
            .pending
            .as_ref()
            .is_some_and(|pending| pending.data.len() >= MAX_OUTPUT_CHUNK_BYTES)
        {
            let Some(mut pending) = self.pending.take() else {
                break;
            };
            let rest: Vec<u8> = pending.data.split_off(MAX_OUTPUT_CHUNK_BYTES);
            let occurred_at = pending.occurred_at.clone();
            self.emit(pending.stream, pending.data, &occurred_at);
            if !rest.is_empty() {
                pending.data = rest;
                pending.since = Instant::now();
                self.pending = Some(pending);
            }
        }
    }

    /// Emit pending output as one chunk.
    pub(crate) fn flush_output(&mut self) {
        if let Some(pending) = self.pending.take() {
            self.emit(pending.stream, pending.data, &pending.occurred_at);
        }
    }

    /// When pending output must be flushed: `None` with nothing pending.
    pub(crate) fn output_due(&self, window: Duration) -> Option<Instant> {
        self.pending.as_ref().map(|pending| pending.since + window)
    }

    /// Whether any output is pending.
    pub(crate) fn has_pending_output(&self) -> bool {
        self.pending.is_some()
    }

    /// Count records the delivery thread could not turn into rows as failed.
    pub(crate) fn account_unbuildable(&mut self, streams: &[DeliveryStream]) {
        for stream in streams {
            self.counts_mut(*stream).failed += 1;
        }
    }

    /// Count a written batch as delivered, less conflicts, or a failed one as failed.
    pub(crate) fn account(
        &mut self,
        batch: &[DeliveryStream],
        outcome: Result<&InsertOutcome, &str>,
    ) {
        match outcome {
            Ok(outcome) => {
                for stream in batch {
                    self.counts_mut(*stream).delivered += 1;
                }
                for conflict in &outcome.conflicts {
                    let stream = stream_of(conflict.table);
                    let counts = self.counts_mut(stream);
                    counts.conflicts += 1;
                    counts.delivered = counts.delivered.saturating_sub(1);
                }
            }
            Err(reason) => {
                for stream in batch {
                    self.counts_mut(*stream).failed += 1;
                }
                self.degraded.get_or_insert_with(|| reason.to_owned());
            }
        }
    }
}
