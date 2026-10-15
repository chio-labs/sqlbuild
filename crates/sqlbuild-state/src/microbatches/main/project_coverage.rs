//! `project_coverage`: fold completion facts and classify uncovered expected intervals.

use std::cmp::Ordering;

use crate::microbatches::_helpers::coverage::{
    Segment, classify_gaps, latest_completion_segments, ordered_boundaries,
};
use crate::microbatches::_helpers::ordering::{extreme, lt, lte, sorted_by_bound};
use crate::microbatches::models::{
    BoundInterval, CompletionFact, CoverageProjection, CoverageSegment, CursorBound, TextInterval,
};

/// Latest-completion segments, the contiguous frontier and the known-missing and unaccounted gaps.
#[must_use]
pub fn project_coverage(
    completions: &[CompletionFact],
    expected: &[BoundInterval],
) -> CoverageProjection {
    let boundaries: Vec<CursorBound> = ordered_boundaries(completions, expected);
    let segments: Vec<Segment> = latest_completion_segments(completions, &boundaries);
    let accounted: Vec<BoundInterval> = segments
        .iter()
        .map(|segment| BoundInterval {
            start: segment.start.clone(),
            end: segment.end.clone(),
        })
        .collect();
    let mut frontier: Option<&CursorBound> = extreme(
        expected.iter().map(|interval| &interval.start),
        Ordering::Less,
    );
    let ordered_accounted: Vec<BoundInterval> = sorted_by_bound(&accounted, |item| &item.start);
    if let Some(mut current) = frontier.filter(|_| !accounted.is_empty()) {
        for interval in &ordered_accounted {
            if !lte(&interval.start, current) {
                break;
            }
            if lt(current, &interval.end) {
                current = &interval.end;
            }
        }
        frontier = Some(current);
    }
    let latest_ordinary_end: Option<&CursorBound> = extreme(
        completions
            .iter()
            .filter(|completion| completion.ordinary)
            .map(|completion| &completion.interval.end),
        Ordering::Greater,
    );
    let (known_missing, unaccounted) = classify_gaps(expected, &accounted, latest_ordinary_end);
    let text = |segment: &Segment| TextInterval {
        start: segment.start.text.clone(),
        end: segment.end.text.clone(),
    };
    CoverageProjection {
        unknown_fingerprints: segments
            .iter()
            .filter(|segment| completions[segment.completion].unknown_fingerprint)
            .map(text)
            .collect(),
        contiguous_frontier: frontier.map(|bound| bound.text.clone()),
        known_missing,
        unaccounted,
        segments: segments
            .iter()
            .map(|segment| CoverageSegment {
                interval: text(segment),
                completion: segment.completion,
            })
            .collect(),
    }
}
