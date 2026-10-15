//! `chunk_text`: split captured text deterministically without splitting code points.

use crate::command_output::_helpers::text::chunk_text;
use crate::command_output::errors::UnencodableText;
use crate::command_output::types::PassText;

/// Chunks of at most `max_bytes` UTF-8 bytes; a wider code point is a chunk of its own.
pub fn chunk_output_text(text: &[u8], max_bytes: i64) -> Result<Vec<PassText>, UnencodableText> {
    chunk_text(text, max_bytes)
}
