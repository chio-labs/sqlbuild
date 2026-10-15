//! Append-only microbatch facts, cursor bounds and the coverage derived from them.

use sqlbuild_cursor::algebra::models::SortKey;

/// One raw cursor bound and the key it sorts and compares by.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CursorBound {
    pub text: String,
    pub key: SortKey,
}

/// A half-open interval between two cursor bounds.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BoundInterval {
    pub start: CursorBound,
    pub end: CursorBound,
}

/// A half-open interval as its raw bound texts.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TextInterval {
    pub start: String,
    pub end: String,
}

/// One partition or synthetic completion that names both partition bounds.
#[derive(Clone, Debug, PartialEq)]
pub struct CompletionFact {
    pub interval: BoundInterval,
    /// Whether this is an ordinary partition completion rather than a synthetic one.
    pub ordinary: bool,
    pub unknown_fingerprint: bool,
    /// `created_at.timestamp()`.
    pub created: f64,
    pub event_id: String,
}

/// One interval and the index of the latest completion accounting for it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CoverageSegment {
    pub interval: TextInterval,
    pub completion: usize,
}

/// Physical and fingerprint coverage derived from completion facts.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct CoverageProjection {
    pub segments: Vec<CoverageSegment>,
    pub contiguous_frontier: Option<String>,
    pub known_missing: Vec<TextInterval>,
    pub unaccounted: Vec<TextInterval>,
    pub unknown_fingerprints: Vec<TextInterval>,
}

/// One projected coverage interval as a replay requirement reads it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CoveragePiece {
    pub interval: BoundInterval,
    pub unknown_fingerprint: bool,
    pub model_version_hash: Option<String>,
}

/// The versions one replay requirement is checked against.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ReplayVersions<'a> {
    pub required: Option<&'a str>,
    pub current: &'a str,
}

/// The derived state of one replay requirement.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReplayState {
    Incomplete,
    VerifiedComplete,
    CompleteWithUnknownFingerprints,
    Superseded,
}

/// A replay requirement's state and the expected intervals still missing or unverified.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ReplayProjection {
    pub state: ReplayState,
    /// Indexes into the expected intervals.
    pub missing: Vec<usize>,
    pub unknown_fingerprints: Vec<usize>,
}

/// One replay requirement event as the latest-requirement selection reads it.
#[derive(Clone, Debug, PartialEq)]
pub struct RequirementFact {
    pub is_requirement: bool,
    pub required_model_version_hash: Option<String>,
    pub created: f64,
    pub event_id: String,
}

/// The fields of a microbatch event's content-addressed identity, in identity order.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MicrobatchEventIdentity {
    pub scope_kind: String,
    pub scope_key: String,
    pub model_name: String,
    pub target_database: Option<String>,
    pub target_schema: Option<String>,
    pub target_name: String,
    pub physical_generation_id: String,
    pub record_type: String,
    pub partition_start: Option<String>,
    pub partition_end: Option<String>,
    pub completion_reason: String,
}

/// A microbatch state table read: its selected columns and scope literals.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScopeRead<'a> {
    pub columns: &'a [String],
    pub scope_kind: &'a str,
    pub scope_key: &'a str,
    /// The generation literal, or `None` for every generation.
    pub generation: Option<&'a str>,
}
