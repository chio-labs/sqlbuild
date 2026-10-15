//! Compiled artifacts queued for one native write, keeping unchanged files when asked.

use std::path::PathBuf;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};

use crate::bindings::_helpers::compile_command::reuse_recording::{
    ArtifactRecorder, artifact_written,
};
use crate::bindings::_helpers::compile_driver::compile_timings::record_compile_timing;
use crate::bindings::_helpers::compile_outputs::artifacts::write_compiled_artifacts;

/// The artifacts of one write group, written together by `flush`.
pub(crate) struct ArtifactBatch<'a> {
    check_existing: bool,
    recorder: ArtifactRecorder<'a>,
    files: Vec<(PathBuf, Vec<u8>)>,
}

impl<'a> ArtifactBatch<'a> {
    pub(crate) fn new(check_existing: bool, recorder: ArtifactRecorder<'a>) -> Self {
        Self {
            check_existing,
            recorder,
            files: Vec::new(),
        }
    }

    /// Queue one artifact with platform line endings, noting its bytes for compile reuse.
    pub(crate) fn queue(&mut self, path: &Bound<'_, PyAny>, contents: Vec<u8>) -> PyResult<()> {
        let contents: Vec<u8> = if cfg!(windows) {
            contents
                .iter()
                .flat_map(|byte| {
                    if *byte == b'\n' {
                        vec![b'\r', b'\n']
                    } else {
                        vec![*byte]
                    }
                })
                .collect()
        } else {
            contents
        };
        artifact_written(self.recorder, path, &contents)?;
        self.files.push((path.extract()?, contents));
        Ok(())
    }

    /// Queue `sql` with trailing whitespace replaced by one newline.
    pub(crate) fn queue_sql(&mut self, path: &Bound<'_, PyAny>, sql: &str) -> PyResult<()> {
        let trimmed: &str =
            sql.trim_end_matches(sqlbuild_core::text::main::python_isspace::python_isspace);
        self.queue(path, format!("{trimmed}\n").into_bytes())
    }

    /// Write every queued artifact natively and empty the queue.
    pub(crate) fn flush(&mut self, py: Python<'_>) -> PyResult<()> {
        if self.files.is_empty() {
            return Ok(());
        }
        let files: Vec<(PathBuf, Vec<u8>)> = std::mem::take(&mut self.files);
        record_compile_timing("physical_write_ms", || {
            write_compiled_artifacts(py, files, self.check_existing).map(|_| ())
        })
    }
}
