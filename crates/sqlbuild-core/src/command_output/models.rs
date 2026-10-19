//! Captured text, record drafts and the bounded delivery queue.

use std::collections::VecDeque;

use crate::command_output::types::PassText;

/// The process stream a fragment was written to.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum OutputStream {
    Stdout,
    Stderr,
}

/// Queue retention class of a record, as `OutputRecordPriority`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RecordPriority {
    Bulk,
    Terminal,
}

/// One record the dispatcher turns into a Python `CommandOutputRecord`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RecordDraft {
    pub sequence: u64,
    pub stream: OutputStream,
    pub message: PassText,
    pub chunk_index: usize,
    pub chunk_count: usize,
    pub priority: RecordPriority,
    /// `dropped_records` of a `command_output_loss` record; zero for ordinary output.
    pub dropped_records: u64,
}

/// Line splitting and record buffering state of one dispatcher.
#[derive(Clone, Debug, PartialEq)]
pub struct OutputBuffer {
    pub max_record_bytes: i64,
    /// Unterminated trailing text per stream: stdout, then stderr.
    pub partials: [PassText; 2],
    pub buffer_stream: Option<OutputStream>,
    pub buffer_text: PassText,
    pub buffer_bytes: usize,
    pub buffer_part_count: usize,
    /// Monotonic seconds when the buffered record started.
    pub buffer_started_at: Option<f64>,
    pub sequence: u64,
}

/// A bounded queue that keeps terminal records over bulk ones, with delivery accounting.
#[derive(Clone, Debug, PartialEq)]
pub struct OutputQueue<T> {
    pub items: VecDeque<(T, RecordPriority)>,
    pub capacity: usize,
    pub accepted: u64,
    pub delivered: u64,
    pub failed: u64,
    pub dropped: u64,
}

impl OutputBuffer {
    /// An empty buffer whose records hold at most `max_record_bytes` UTF-8 bytes.
    pub fn new(max_record_bytes: i64) -> Self {
        Self {
            max_record_bytes,
            partials: [PassText::new(), PassText::new()],
            buffer_stream: None,
            buffer_text: PassText::new(),
            buffer_bytes: 0,
            buffer_part_count: 0,
            buffer_started_at: None,
            sequence: 0,
        }
    }
}

impl<T> OutputQueue<T> {
    /// An empty queue holding at most `capacity` records.
    pub fn new(capacity: usize) -> Self {
        Self {
            items: VecDeque::new(),
            capacity,
            accepted: 0,
            delivered: 0,
            failed: 0,
            dropped: 0,
        }
    }
}

/// The buffer after one call, the records it produced in order, and a failure part-way through.
#[derive(Clone, Debug, PartialEq)]
pub struct BufferOutcome {
    pub buffer: OutputBuffer,
    pub drafts: Vec<RecordDraft>,
    /// The encode failure Python raised after `drafts` were already enqueued.
    pub error: Option<crate::command_output::errors::UnencodableText>,
}

/// What an idle delivery worker does next.
#[derive(Clone, Debug, PartialEq)]
pub enum IdleStep {
    /// Wait for new records, at most this many seconds when a buffered record is pending.
    Wait(Option<f64>),
    /// The buffered record became due and was flushed into these records.
    Flushed(Vec<RecordDraft>),
}

/// A `CommandOutputRecord`'s fields as the validation sees them; `None` marks a wrong type.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct RecordShape {
    /// `invocation_id`, `producer` and `producer_version`, each when it is a `str`.
    pub identity: [(&'static str, Option<String>); 3],
    /// `run_id`: absent (`None`) or a `str`; `Some(None)` for another type.
    pub run_id: Option<Option<String>>,
    pub sequence: Option<i64>,
    pub occurred_at_is_utc: bool,
    pub stream_is_known: bool,
    pub message_is_text: bool,
    pub data_is_bytes: bool,
    pub chunk_index: Option<i64>,
    pub chunk_count: Option<i64>,
    pub dropped_records: Option<i64>,
    pub priority_is_known: bool,
    pub record_type: Option<String>,
    pub schema_version: Option<i64>,
}
