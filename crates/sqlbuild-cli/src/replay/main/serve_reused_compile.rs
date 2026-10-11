//! Replay the stored compile when the launch record still matches, as the Python CLI would.

use std::io;
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime};

use crate::compute_logs::main::finish_capture::finish_capture;
use crate::compute_logs::main::start_capture::start_capture;
use crate::compute_logs::models::{CaptureEnd, CaptureStart, OpenCapture};
use crate::replay::_helpers::console::{redirected_output_files, write_streams};
use crate::replay::_helpers::records::{read_record, reuse_rules};
use crate::replay::_helpers::serving::{served, stored_output};
use crate::replay::constants::OUTPUT_FAILURE_EXIT_CODE;

/// The exit code of a natively served reuse hit, or `None` to hand the invocation to Python.
pub fn serve_reused_compile(
    record_path: &Path,
    key: &str,
    started: (Instant, SystemTime),
) -> Option<i64> {
    let record = read_record(record_path, key)?;
    let rules = reuse_rules(&record.rules, redirected_output_files());
    let output = stored_output(&record, &rules)?;
    let mut invocation = served(&record, &output, started.0)?;
    let capture: Option<io::Result<OpenCapture>> = record.capture.as_ref().map(|capture| {
        start_capture(CaptureStart {
            root: PathBuf::from(&capture.root),
            command: capture.command.clone(),
            project_dir: capture.project_dir.clone(),
            target: capture.target.clone(),
            started_at: started.1,
        })
    });
    if let Err(error) = write_streams(&invocation.stderr, &invocation.stdout) {
        let message = format!("Compile replay failed: could not write output: {error}\n");
        let _ = write_streams(&message, "");
        invocation.stderr.push_str(&message);
        invocation.exit_code = OUTPUT_FAILURE_EXIT_CODE;
    }
    if let Some(Ok(capture)) = capture {
        let _ = finish_capture(
            capture,
            &CaptureEnd {
                stdout: invocation.stdout.into_bytes(),
                stderr: invocation.stderr.into_bytes(),
                exit_code: invocation.exit_code,
            },
        );
    }
    Some(invocation.exit_code)
}
