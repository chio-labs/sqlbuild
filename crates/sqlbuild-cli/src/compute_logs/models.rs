//! A compute log capture's identity and the metadata it publishes.

use std::fs::File;
use std::path::PathBuf;
use std::time::SystemTime;

/// What one capture records before its command runs, as Python's `CaptureMetadata`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CaptureStart {
    /// The resolved compute log root, `<project>/logs`.
    pub root: PathBuf,
    pub command: String,
    pub project_dir: String,
    pub target: Option<String>,
    pub started_at: SystemTime,
}

/// What the finished command adds, as Python's `FinalCaptureMetadata`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CaptureEnd {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub exit_code: i64,
}

/// A published, incomplete capture and its open stream files.
#[derive(Debug)]
pub struct OpenCapture {
    pub start: CaptureStart,
    /// The invocation id naming the capture directory, as `uuid4().hex`.
    pub invocation_id: String,
    pub directory: PathBuf,
    /// `stdout.log`, `stderr.log` and `diagnostics.jsonl`.
    pub streams: Vec<File>,
}

/// One timezone-aware or naive instant of capture metadata.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CaptureInstant {
    /// Microseconds since the Unix epoch; meaningful only when `aware`.
    pub micros: i64,
    pub aware: bool,
    /// `isoformat()` with `+00:00` written as `Z`, as `metadata.json` stores it.
    pub text: String,
}

/// What `FinalCaptureMetadata` adds once the capture's streams are closed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CaptureCompletion {
    pub completed_at: CaptureInstant,
    pub exit_code: i64,
    pub stdout_bytes: i64,
    pub stderr_bytes: i64,
    pub diagnostics_bytes: i64,
}

/// Python's `CaptureMetadata`, or `FinalCaptureMetadata` when `completion` is present.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CaptureDocument {
    pub format_version: i64,
    pub invocation_id: String,
    pub command: String,
    pub project_dir: String,
    pub started_at: CaptureInstant,
    pub capture_date: String,
    pub target: Option<String>,
    pub run_id: Option<String>,
    pub completion: Option<CaptureCompletion>,
}

/// One capture beneath a compute log root, as `CaptureInventoryItem`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InventoryEntry {
    pub document: CaptureDocument,
    pub path: PathBuf,
    pub is_complete: bool,
}

/// Raw bytes read from one stream at an exclusive cursor, as `ComputeLogReadChunk`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StreamChunk {
    pub data: Vec<u8>,
    pub next_cursor: u64,
    pub is_complete: bool,
}

/// Captures one retention pass deleted and the counts it kept, as `PruneResult`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct PruneOutcome {
    pub deleted_invocation_ids: Vec<String>,
    pub retained_complete_count: usize,
    pub retained_incomplete_count: usize,
}
