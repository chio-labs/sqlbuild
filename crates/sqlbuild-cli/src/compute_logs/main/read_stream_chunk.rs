//! `read`: at most `max_bytes` of one stream from an exact byte cursor.

use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

use crate::compute_logs::_helpers::paths::{
    ensure_contained, existing_capture, read_bounds, validate_capture_id,
};
use crate::compute_logs::constants::COMPLETE_FILE_NAME;
use crate::compute_logs::errors::{ComputeLogError, ComputeLogErrorKind};
use crate::compute_logs::models::StreamChunk;

/// The chunk at `cursor` of the capture's `file_name` stream.
pub fn read_stream_chunk(
    root: &Path,
    (invocation_id, file_name): (&str, &str),
    cursor: i64,
    max_bytes: i64,
) -> Result<StreamChunk, ComputeLogError> {
    validate_capture_id(invocation_id)?;
    let (cursor, limit) = read_bounds(cursor, max_bytes)?;
    let directory = existing_capture(root, invocation_id)?;
    let path = directory.join(file_name);
    let marker = directory.join(COMPLETE_FILE_NAME);
    ensure_contained(root, &path)?;
    ensure_contained(root, &marker)?;
    let is_complete = marker.is_file();
    if !path.exists() {
        return Ok(StreamChunk {
            data: Vec::new(),
            next_cursor: cursor,
            is_complete,
        });
    }
    let size = std::fs::metadata(&path)?.len();
    if cursor > size {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::InvalidCursor,
            format!("cursor {cursor} is beyond current stream size {size}"),
        ));
    }
    let mut file = std::fs::File::open(&path)?;
    file.seek(SeekFrom::Start(cursor))?;
    let mut data: Vec<u8> = Vec::new();
    Read::by_ref(&mut file).take(limit).read_to_end(&mut data)?;
    let next_cursor = file.stream_position()?;
    Ok(StreamChunk {
        data,
        next_cursor,
        is_complete,
    })
}
