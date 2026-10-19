use crate::records::models::{OutputStream, RecallValue};
use crate::writer::models::{DeliveryStream, Priority, SetupOutcome};

/// What one recorded session left in the store.
#[derive(Debug, PartialEq)]
pub(crate) struct RecordedSession {
    pub(crate) setup: Option<SetupOutcome>,
    pub(crate) lost: (u64, u64),
    pub(crate) output_fully_delivered: bool,
    pub(crate) transcript: (Vec<u8>, bool),
    pub(crate) stdout: Vec<u8>,
    pub(crate) facts: Vec<Vec<RecallValue>>,
}

pub(crate) struct DisplacementTestCase {
    pub(crate) description: &'static str,
    pub(crate) capacity: usize,
    pub(crate) pushes: &'static [(DeliveryStream, Priority)],
    pub(crate) expected_dropped: Vec<(DeliveryStream, u64)>,
    pub(crate) expected_taken: Vec<DeliveryStream>,
}

pub(crate) struct ChunkingTestCase {
    pub(crate) description: &'static str,
    pub(crate) writes: Vec<(OutputStream, Vec<u8>)>,
    pub(crate) expected_chunks: Vec<[Option<RecallValue>; 3]>,
}

pub(crate) struct SessionTestCase {
    pub(crate) description: &'static str,
    pub(crate) output: Vec<(OutputStream, Vec<u8>)>,
    pub(crate) expected_session: RecordedSession,
}

pub(crate) struct UnwritableTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_permission_and_degraded: (bool, bool),
}

pub(crate) struct HeldLockTestCase {
    pub(crate) description: &'static str,
    pub(crate) shutdown_ms: u64,
    pub(crate) expected_degraded: bool,
}

pub(crate) struct CorruptStoreTestCase {
    pub(crate) description: &'static str,
    pub(crate) expected_notices: usize,
    pub(crate) expected_moved: bool,
    pub(crate) expected_rows: Vec<Vec<RecallValue>>,
}

pub(crate) struct ArtifactSizeTestCase {
    pub(crate) description: &'static str,
    pub(crate) length: usize,
    pub(crate) expected_counts: (u64, u64, u64),
}

pub(crate) struct OutputDropTestCase {
    pub(crate) description: &'static str,
    pub(crate) capacity: usize,
    pub(crate) chunks: usize,
    pub(crate) expected_drops: (u64, Vec<Option<RecallValue>>),
}
