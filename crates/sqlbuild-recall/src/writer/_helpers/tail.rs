//! The bounded ring holding the end of one output stream past its head limit until the session closes.

use std::collections::VecDeque;

use crate::records::models::{OmittedOutput, OutputChunk, OutputStream};

/// Bytes kept from the end of a stream, with the sequence reserved when they were written.
#[derive(Debug)]
pub(crate) struct TailSegment {
    pub(crate) sequence: u64,
    pub(crate) byte_offset: u64,
    pub(crate) occurred_at: String,
    pub(crate) data: Vec<u8>,
    /// Bytes at the front already evicted.
    start: usize,
}

impl TailSegment {
    pub(crate) fn new(sequence: u64, byte_offset: u64, occurred_at: String) -> Self {
        Self {
            sequence,
            byte_offset,
            occurred_at,
            data: Vec::new(),
            start: 0,
        }
    }

    fn kept(&self) -> usize {
        self.data.len() - self.start
    }
}

/// One stream's tail: at most `capacity` bytes, the reserved gap sequence and what was left out.
#[derive(Debug, Default)]
pub(crate) struct TailRing {
    capacity: usize,
    segments: VecDeque<TailSegment>,
    bytes: usize,
    /// The gap's sequence, stream offset and time, reserved when the stream passed its head limit.
    marker: Option<(u64, u64, String)>,
    omitted_bytes: u64,
    evicted_sequences: u64,
}

impl TailRing {
    pub(crate) fn new(capacity: usize) -> Self {
        Self {
            capacity,
            ..Self::default()
        }
    }

    pub(crate) fn capacity(&self) -> usize {
        self.capacity
    }

    /// Whether the stream has passed its head limit.
    pub(crate) fn active(&self) -> bool {
        self.marker.is_some()
    }

    /// Reserve the gap's position, right after the head.
    pub(crate) fn activate(&mut self, sequence: u64, byte_offset: u64, occurred_at: String) {
        self.marker = Some((sequence, byte_offset, occurred_at));
    }

    /// Leave out `bytes` that never entered the ring.
    pub(crate) fn omit(&mut self, bytes: usize) {
        self.omitted_bytes += bytes as u64;
    }

    /// Evict from the front until at most `limit` bytes remain.
    pub(crate) fn evict_to(&mut self, limit: usize) {
        while self.bytes > limit {
            let Some(front) = self.segments.front_mut() else {
                break;
            };
            let removed: usize = (self.bytes - limit).min(front.kept());
            front.start += removed;
            front.byte_offset += removed as u64;
            self.bytes -= removed;
            self.omitted_bytes += removed as u64;
            if front.kept() == 0 {
                drop(self.segments.pop_front());
                self.evicted_sequences += 1;
            }
        }
    }

    /// Room left in the newest segment for contiguous bytes, below `chunk_bytes`.
    pub(crate) fn room(&self, chunk_bytes: usize) -> usize {
        self.segments
            .back()
            .map_or(0, |segment| chunk_bytes.saturating_sub(segment.data.len()))
    }

    pub(crate) fn open(&mut self, segment: TailSegment) {
        self.segments.push_back(segment);
    }

    /// Append to the newest segment; the caller checked `room`.
    pub(crate) fn extend(&mut self, data: &[u8]) {
        if let Some(segment) = self.segments.back_mut() {
            segment.data.extend_from_slice(data);
            self.bytes += data.len();
        }
    }

    /// The gap chunk and the kept tail chunks of `stream`, leaving the ring empty and inactive.
    pub(crate) fn take(&mut self, stream: OutputStream) -> Vec<OutputChunk> {
        let Some((sequence, byte_offset, occurred_at)) = self.marker.take() else {
            return Vec::new();
        };
        let mut chunks: Vec<OutputChunk> = vec![OutputChunk {
            sequence,
            stream,
            occurred_at,
            data: Vec::new(),
            byte_offset,
            dropped_before: 0,
            omitted: Some(OmittedOutput {
                bytes: std::mem::take(&mut self.omitted_bytes),
                sequences: std::mem::take(&mut self.evicted_sequences) + 1,
            }),
        }];
        chunks.extend(self.segments.drain(..).map(|segment| OutputChunk {
            sequence: segment.sequence,
            stream,
            occurred_at: segment.occurred_at,
            data: segment.data[segment.start..].to_vec(),
            byte_offset: segment.byte_offset,
            dropped_before: 0,
            omitted: None,
        }));
        self.bytes = 0;
        chunks
    }
}
