//! The note `sqb recall output` prints where output past `max_output_bytes` was left out.

use crate::store::constants::{BINARY_UNIT_STEP, BINARY_UNITS, DECIMAL_UNIT_STEP, DECIMAL_UNITS};
use crate::store::models::StoredChunk;

/// `23.6 MB`: decimal units with one decimal, whole bytes below a kilobyte.
fn decimal_size(bytes: u64) -> String {
    let mut value = bytes as f64;
    let mut unit: Option<&str> = None;
    for candidate in DECIMAL_UNITS {
        if value < DECIMAL_UNIT_STEP {
            break;
        }
        value /= DECIMAL_UNIT_STEP;
        unit = Some(candidate);
    }
    unit.map_or_else(
        || format!("{bytes} bytes"),
        |unit| format!("{value:.1} {unit}"),
    )
}

/// `1 MiB`: the largest binary unit dividing `bytes` exactly.
fn binary_size(bytes: u64) -> String {
    let mut value = bytes;
    let mut unit: Option<&str> = None;
    for candidate in BINARY_UNITS {
        if value == 0 || !value.is_multiple_of(BINARY_UNIT_STEP) {
            break;
        }
        value /= BINARY_UNIT_STEP;
        unit = Some(candidate);
    }
    unit.map_or_else(
        || format!("{bytes} bytes"),
        |unit| format!("{value} {unit}"),
    )
}

/// One line naming the bytes of `stream` left out between the kept `head` and `tail`.
pub(crate) fn truncation_note(stream: &str, omitted: u64, (head, tail): (u64, u64)) -> String {
    let kept: String = if head == tail {
        format!("kept the first and last {}", binary_size(head))
    } else {
        format!(
            "kept the first {} and the last {}",
            binary_size(head),
            binary_size(tail)
        )
    };
    format!(
        "\u{2026} {} of {stream} not recorded ({kept}). Raise [recall] max_output_bytes to keep \
         more.\n",
        decimal_size(omitted)
    )
}

/// Bytes of `stream` in `chunks`.
fn stream_bytes(chunks: &[StoredChunk], stream: &str) -> u64 {
    chunks
        .iter()
        .filter(|chunk| chunk.stream == stream)
        .map(|chunk| chunk.data.len() as u64)
        .sum()
}

/// The chunks' bytes in order, with a note line where output was left out.
pub(crate) fn with_truncation_notes(chunks: &[StoredChunk]) -> Vec<u8> {
    let mut data: Vec<u8> = Vec::with_capacity(chunks.iter().map(|chunk| chunk.data.len()).sum());
    for (position, chunk) in chunks.iter().enumerate() {
        data.extend_from_slice(&chunk.data);
        let omitted: u64 = chunk
            .omitted_bytes
            .filter(|bytes| *bytes > 0)
            .map_or(0, i64::unsigned_abs);
        if omitted == 0 {
            continue;
        }
        if data.last().is_some_and(|byte| *byte != b'\n') {
            data.push(b'\n');
        }
        let kept = (
            stream_bytes(&chunks[..position], &chunk.stream),
            stream_bytes(&chunks[position + 1..], &chunk.stream),
        );
        data.extend_from_slice(truncation_note(&chunk.stream, omitted, kept).as_bytes());
    }
    data
}
