//! The bounded priority queue and the output coalescer, guarded together by one mutex.

use std::collections::VecDeque;
use std::time::{Duration, Instant, SystemTime};

use serde_json::{Map, Value};

use crate::records::constants::{DROPPED_BEFORE_COLUMN, MAX_OUTPUT_CHUNK_BYTES};
use crate::records::main::format_timestamp::format_timestamp;
use crate::records::main::invocation_row::invocation_row;
use crate::records::main::output_row::output_row;
use crate::records::models::{
    DeliveryCounts, InvocationContext, OutputChunk, OutputStream, RecallRow, RecallValue,
    RowEnvelope,
};
use crate::store::models::InsertOutcome;
use crate::writer::_helpers::delivery::{record_stream, stream_of};
use crate::writer::_helpers::tail::{TailRing, TailSegment};
use crate::writer::constants::{PENDING_EVENT_BYTES, QUEUE_BYTE_CAPACITY, QUEUE_RECORD_CAPACITY};
use crate::writer::models::{DeliveryStream, Priority};
use crate::writer::types::PendingLifecycleEvent;

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
    /// An event the lifecycle replacement sink decides on when its batch is built, by publication sequence.
    Pending(u64, Box<dyn PendingLifecycleEvent>),
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
            Payload::Event(_) | Payload::Pending(..) | Payload::Sql(_) => &[],
        }
    }

    fn row_count(&self) -> usize {
        match &self.payload {
            Payload::Rows(rows) => rows.len(),
            Payload::Event(_) | Payload::Pending(..) => 1,
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
    /// Bytes of each stream recorded from its start, pending or emitted.
    captured: [usize; 2],
    /// Bytes of each stream recorded from its start; `None` records everything.
    head_limit: Option<usize>,
    /// The end of each stream past its head limit, kept until the session closes.
    tails: [TailRing; 2],
    /// The stream whose newest tail segment holds the latest sequence, so it may grow.
    tail_open: Option<OutputStream>,
    unreported_output_drops: u64,
    pub(crate) diagnostic_sequence: u64,
    /// The publication sequence of the next event for the lifecycle replacement.
    pending_sequence: u64,
    pub(crate) closing: bool,
    pub(crate) deadline: Option<Instant>,
    pub(crate) finished: bool,
    pub(crate) rejecting: bool,
    pub(crate) degraded: Option<String>,
    /// Store notices the user should see, such as a corrupt store moved aside.
    pub(crate) notices: Vec<String>,
    /// The context row's content while its replacement-filter flag is still unknown.
    pub(crate) held_context: Option<InvocationContext>,
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
            captured: [0; 2],
            head_limit: None,
            tails: Default::default(),
            tail_open: None,
            unreported_output_drops: 0,
            diagnostic_sequence: 0,
            pending_sequence: 0,
            closing: false,
            deadline: None,
            finished: false,
            rejecting: false,
            degraded: None,
            notices: Vec::new(),
            held_context: None,
            capacity,
        }
    }

    /// The same state recording at most `limit` bytes of each output stream: the first half and the last half; `None` records everything.
    pub(crate) fn with_output_limit(mut self, limit: Option<u64>) -> Self {
        let Some(limit) = limit.map(|limit| usize::try_from(limit).unwrap_or(usize::MAX)) else {
            self.head_limit = None;
            return self;
        };
        let tail: usize = limit / 2;
        self.head_limit = Some(limit - tail);
        self.tails = [TailRing::new(tail), TailRing::new(tail)];
        self
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

    /// Queue an event for the lifecycle replacement, numbered in publication order.
    pub(crate) fn push_pending(
        &mut self,
        event: Box<dyn PendingLifecycleEvent>,
        priority: Priority,
    ) {
        let sequence: u64 = self.pending_sequence;
        self.pending_sequence += 1;
        self.push_record(
            Queued {
                payload: Payload::Pending(sequence, event),
                stream: DeliveryStream::Events,
                bytes: PENDING_EVENT_BYTES,
            },
            priority,
        );
    }

    pub(crate) fn queued(&self) -> usize {
        self.records
    }

    /// Whether output waits in the queue until discovery decides whether a replacement sink filters it.
    fn holding_output(&self) -> bool {
        self.held_context.is_some()
    }

    /// Records a batch may take now: output is held while the context row is.
    pub(crate) fn ready(&self) -> usize {
        if self.holding_output() {
            self.records - self.buckets[Priority::Output as usize].len()
        } else {
            self.records
        }
    }

    /// Up to `limit` rows, highest priority first; held output stays queued.
    pub(crate) fn take_batch(&mut self, limit: usize) -> Vec<Queued> {
        let mut batch: Vec<Queued> = Vec::new();
        let mut rows = 0;
        let held: Option<usize> = self.holding_output().then_some(Priority::Output as usize);
        for (index, bucket) in self.buckets.iter_mut().enumerate().rev() {
            if held == Some(index) {
                continue;
            }
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

    fn push_chunk(&mut self, mut chunk: OutputChunk) {
        chunk.dropped_before = std::mem::take(&mut self.unreported_output_drops);
        let row = output_row(&self.envelope, &chunk);
        self.push(vec![row], DeliveryStream::Output, Priority::Output);
    }

    fn emit(&mut self, stream: OutputStream, data: Vec<u8>, occurred_at: &str) {
        let index = usize::from(stream == OutputStream::Stderr);
        let chunk = OutputChunk {
            sequence: self.next_sequence,
            stream,
            occurred_at: occurred_at.to_owned(),
            byte_offset: self.offsets[index],
            dropped_before: 0,
            data,
            omitted: None,
        };
        self.next_sequence += 1;
        self.tail_open = None;
        self.offsets[index] += chunk.data.len() as u64;
        self.push_chunk(chunk);
    }

    /// Accept `data` written to `stream`: a stream switch flushes the other stream first, so the shared sequence preserves interleaving; full chunks are emitted at once. Past the head limit, bytes go to the stream's tail ring.
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
        let index = usize::from(stream == OutputStream::Stderr);
        let Some(head_limit) = self.head_limit else {
            self.record_output(stream, data, now);
            return;
        };
        let room: usize = head_limit.saturating_sub(self.captured[index]);
        let (head, rest) = data.split_at(room.min(data.len()));
        self.captured[index] += head.len();
        self.record_output(stream, head, now);
        if !rest.is_empty() {
            self.tail_output(stream, rest, now);
        }
        if self.closing {
            self.flush_tails();
        }
    }

    /// Keep the newest bytes of `stream` past its head limit in its ring, each run under a sequence reserved now so the global order holds; what the ring cannot hold is counted as omitted.
    fn tail_output(&mut self, stream: OutputStream, data: &[u8], now: SystemTime) {
        let index = usize::from(stream == OutputStream::Stderr);
        let occurred_at: String = format_timestamp(now);
        if !self.tails[index].active() {
            self.flush_output();
            self.tails[index].activate(
                self.next_sequence,
                self.offsets[index],
                occurred_at.clone(),
            );
            self.next_sequence += 1;
            self.tail_open = None;
        }
        let capacity: usize = self.tails[index].capacity();
        let skipped: usize = data.len().saturating_sub(capacity);
        let mut rest: &[u8] = &data[skipped..];
        if skipped > 0 {
            self.tails[index].evict_to(0);
            self.tails[index].omit(skipped);
            self.offsets[index] += skipped as u64;
            self.tail_open = None;
        }
        self.tails[index].evict_to(capacity - rest.len());
        while !rest.is_empty() {
            let room: usize = if self.tail_open == Some(stream) {
                self.tails[index].room(MAX_OUTPUT_CHUNK_BYTES)
            } else {
                0
            };
            if room == 0 {
                self.tails[index].open(TailSegment::new(
                    self.next_sequence,
                    self.offsets[index],
                    occurred_at.clone(),
                ));
                self.next_sequence += 1;
                self.tail_open = Some(stream);
                continue;
            }
            let (taken, after) = rest.split_at(room.min(rest.len()));
            self.tails[index].extend(taken);
            self.offsets[index] += taken.len() as u64;
            rest = after;
        }
    }

    /// Queue each stream's gap and kept tail, as when the session closes.
    pub(crate) fn flush_tails(&mut self) {
        self.flush_output();
        for stream in [OutputStream::Stdout, OutputStream::Stderr] {
            let index = usize::from(stream == OutputStream::Stderr);
            let chunks: Vec<OutputChunk> = self.tails[index].take(stream);
            for chunk in chunks {
                self.push_chunk(chunk);
            }
        }
        self.tail_open = None;
    }

    /// Chunk `data` without copying it more than once: fill the pending chunk, emit full chunks straight from `data`, keep the remainder pending.
    fn record_output(&mut self, stream: OutputStream, data: &[u8], now: SystemTime) {
        if data.is_empty() {
            return;
        }
        let mut rest: &[u8] = data;
        if let Some(pending) = self.pending.as_mut() {
            let room: usize = MAX_OUTPUT_CHUNK_BYTES.saturating_sub(pending.data.len());
            let (head, tail) = rest.split_at(room.min(rest.len()));
            pending.data.extend_from_slice(head);
            rest = tail;
            if pending.data.len() >= MAX_OUTPUT_CHUNK_BYTES {
                self.flush_output();
            }
        }
        if rest.is_empty() {
            return;
        }
        let occurred_at: String = format_timestamp(now);
        let (full, remainder) = rest.as_chunks::<MAX_OUTPUT_CHUNK_BYTES>();
        for chunk in full {
            self.emit(stream, chunk.to_vec(), &occurred_at);
        }
        if !remainder.is_empty() {
            self.pending = Some(Pending {
                stream,
                data: remainder.to_vec(),
                since: Instant::now(),
                occurred_at,
            });
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

    /// Count records a replacement sink chose not to store as filtered.
    pub(crate) fn account_filtered(&mut self, streams: &[DeliveryStream]) {
        for stream in streams {
            self.counts_mut(*stream).filtered += 1;
        }
    }

    /// Queue the held context row, recording whether a replacement sink filters this invocation.
    pub(crate) fn release_context(&mut self, filter_active: bool) {
        if let Some(mut context) = self.held_context.take() {
            context.recall_filter_active = filter_active;
            let row = invocation_row(&self.envelope, &context);
            self.push(vec![row], DeliveryStream::Invocation, Priority::Context);
        }
    }

    /// Count records the delivery thread could not turn into rows as failed.
    pub(crate) fn account_unbuildable(&mut self, streams: &[DeliveryStream]) {
        for stream in streams {
            self.counts_mut(*stream).failed += 1;
        }
    }

    /// Count a written batch as delivered, less conflicts and records of tables whose insert failed, or a failed one as failed.
    pub(crate) fn account(
        &mut self,
        batch: &[DeliveryStream],
        outcome: Result<&InsertOutcome, &str>,
    ) {
        match outcome {
            Ok(outcome) => {
                let failed: Vec<DeliveryStream> = outcome
                    .failed
                    .iter()
                    .filter_map(|table| record_stream(*table))
                    .collect();
                for stream in batch {
                    if failed.contains(stream) {
                        self.counts_mut(*stream).failed += 1;
                    } else {
                        self.counts_mut(*stream).delivered += 1;
                    }
                }
                if let Some(reason) = &outcome.failure {
                    self.degraded.get_or_insert_with(|| reason.clone());
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
