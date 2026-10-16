//! The boundary sweep and gap classification behind microbatch coverage projection.

use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashSet};

use crate::microbatches::_helpers::ordering::{key_cmp, lt, lte, sorted_by_bound};
use crate::microbatches::models::{BoundInterval, CompletionFact, CursorBound, TextInterval};

/// One swept segment between adjacent boundaries and its latest active completion.
pub(crate) struct Segment {
    pub(crate) start: CursorBound,
    pub(crate) end: CursorBound,
    pub(crate) completion: usize,
}

fn text_interval(start: &CursorBound, end: &CursorBound) -> TextInterval {
    TextInterval {
        start: start.text.clone(),
        end: end.text.clone(),
    }
}

/// Every distinct bound text, sorted by key.
pub(crate) fn ordered_boundaries(
    completions: &[CompletionFact],
    expected: &[BoundInterval],
) -> Vec<CursorBound> {
    let mut boundaries: Vec<CursorBound> = Vec::new();
    let mut seen: HashSet<&str> = HashSet::new();
    let intervals = completions
        .iter()
        .map(|completion| &completion.interval)
        .chain(expected);
    for interval in intervals {
        for bound in [&interval.start, &interval.end] {
            if seen.insert(bound.text.as_str()) {
                boundaries.push(bound.clone());
            }
        }
    }
    boundaries.sort_by(|left, right| {
        key_cmp(&left.key, &right.key).then_with(|| left.text.cmp(&right.text))
    });
    boundaries
}

/// Sweep adjacent boundaries, keeping the most recently created active completion.
pub(crate) fn latest_completion_segments(
    completions: &[CompletionFact],
    boundaries: &[CursorBound],
) -> Vec<Segment> {
    let mut latest_order: Vec<usize> = (0..completions.len()).collect();
    latest_order.sort_by(|left, right| {
        let (left, right) = (&completions[*left], &completions[*right]);
        left.created
            .partial_cmp(&right.created)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.event_id.cmp(&right.event_id))
    });
    let mut rank: Vec<usize> = vec![0; completions.len()];
    for (position, index) in latest_order.into_iter().enumerate() {
        rank[index] = position;
    }
    let mut by_start: Vec<usize> = (0..completions.len()).collect();
    by_start.sort_by(|left, right| {
        key_cmp(
            &completions[*left].interval.start.key,
            &completions[*right].interval.start.key,
        )
    });
    let mut active: BinaryHeap<(usize, usize)> = BinaryHeap::new();
    let mut next: usize = 0;
    let mut segments: Vec<Segment> = Vec::new();
    for pair in boundaries.windows(2) {
        let (start, end) = (&pair[0], &pair[1]);
        while next < by_start.len() && lte(&completions[by_start[next]].interval.start, start) {
            active.push((rank[by_start[next]], by_start[next]));
            next += 1;
        }
        while let Some((_, top)) = active.peek() {
            if lte(end, &completions[*top].interval.end) {
                break;
            }
            active.pop();
        }
        if let Some((_, top)) = active.peek() {
            segments.push(Segment {
                start: start.clone(),
                end: end.clone(),
                completion: *top,
            });
        }
    }
    segments
}

/// The uncovered parts of each expected interval, split into known-missing and unaccounted.
pub(crate) fn classify_gaps(
    expected: &[BoundInterval],
    accounted: &[BoundInterval],
    latest_ordinary_end: Option<&CursorBound>,
) -> (Vec<TextInterval>, Vec<TextInterval>) {
    let ordered_expected: Vec<BoundInterval> = sorted_by_bound(expected, |item| &item.start);
    let ordered_accounted: Vec<BoundInterval> = sorted_by_bound(accounted, |item| &item.start);
    let mut known_missing: Vec<TextInterval> = Vec::new();
    let mut unaccounted: Vec<TextInterval> = Vec::new();
    let mut accounted_index: usize = 0;
    for expected in &ordered_expected {
        while accounted_index < ordered_accounted.len()
            && lte(&ordered_accounted[accounted_index].end, &expected.start)
        {
            accounted_index += 1;
        }
        let mut frontier: &CursorBound = &expected.start;
        let mut gaps: Vec<(&CursorBound, &CursorBound)> = Vec::new();
        for interval in &ordered_accounted[accounted_index..] {
            if !lt(&interval.start, &expected.end) {
                break;
            }
            if lt(frontier, &interval.start) {
                gaps.push((frontier, &interval.start));
            }
            if lt(frontier, &interval.end) {
                frontier = &interval.end;
            }
            if lte(&expected.end, frontier) {
                break;
            }
        }
        if lt(frontier, &expected.end) {
            gaps.push((frontier, &expected.end));
        }
        for (start, end) in gaps {
            let accounted_before: bool = accounted_index > 0 || lt(&expected.start, start);
            let known: bool =
                accounted_before && latest_ordinary_end.is_some_and(|latest| lte(end, latest));
            let gap: TextInterval = text_interval(start, end);
            if known {
                known_missing.push(gap);
            } else {
                unaccounted.push(gap);
            }
        }
    }
    (known_missing, unaccounted)
}
