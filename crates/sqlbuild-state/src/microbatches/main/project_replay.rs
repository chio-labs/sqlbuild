//! `project_replay`: derive a replay requirement's completion without mutable status.

use crate::microbatches::_helpers::ordering::{lt, lte, sorted_by_bound};
use crate::microbatches::models::{
    BoundInterval, CoveragePiece, CursorBound, ReplayProjection, ReplayState, ReplayVersions,
};

fn fully_covered(expected: &BoundInterval, pieces: &[&CoveragePiece]) -> bool {
    let mut frontier: &CursorBound = &expected.start;
    for piece in sorted_by_bound(pieces, |piece| &piece.interval.start) {
        if lte(&piece.interval.end, frontier) {
            continue;
        }
        if lt(frontier, &piece.interval.start) {
            return false;
        }
        frontier = &piece.interval.end;
        if lte(&expected.end, frontier) {
            return true;
        }
    }
    false
}

/// Superseded for another version; otherwise which expected intervals are missing or unverified.
#[must_use]
pub fn project_replay(
    versions: ReplayVersions<'_>,
    expected: &[BoundInterval],
    coverage: &[CoveragePiece],
) -> ReplayProjection {
    if versions.required != Some(versions.current) {
        return ReplayProjection {
            state: ReplayState::Superseded,
            missing: Vec::new(),
            unknown_fingerprints: Vec::new(),
        };
    }
    let mut missing: Vec<usize> = Vec::new();
    let mut unknown: Vec<usize> = Vec::new();
    for (index, interval) in expected.iter().enumerate() {
        let pieces: Vec<&CoveragePiece> = coverage
            .iter()
            .filter(|piece| {
                lt(&piece.interval.start, &interval.end) && lt(&interval.start, &piece.interval.end)
            })
            .collect();
        if !fully_covered(interval, &pieces) {
            missing.push(index);
        } else if pieces.iter().any(|piece| piece.unknown_fingerprint) {
            unknown.push(index);
        } else if pieces
            .iter()
            .any(|piece| piece.model_version_hash.as_deref() != Some(versions.current))
        {
            missing.push(index);
        }
    }
    let state: ReplayState = if !missing.is_empty() {
        ReplayState::Incomplete
    } else if !unknown.is_empty() {
        ReplayState::CompleteWithUnknownFingerprints
    } else {
        ReplayState::VerifiedComplete
    };
    ReplayProjection {
        state,
        missing,
        unknown_fingerprints: unknown,
    }
}
