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
