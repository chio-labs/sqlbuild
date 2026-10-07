//! Python's `difflib.get_close_matches` with the default `SequenceMatcher` settings.

use crate::text::_helpers::sequence_matcher::{ScoredCandidate, scored_candidates};

/// The best `count` candidates whose similarity to `word` reaches `cutoff`, best first.
pub fn close_matches(word: &str, possibilities: &[&str], count: usize, cutoff: f64) -> Vec<String> {
    let mut scored: Vec<ScoredCandidate<'_>> = scored_candidates(word, possibilities, cutoff);
    scored.sort_by(|left, right| {
        right
            .score
            .total_cmp(&left.score)
            .then_with(|| right.candidate.cmp(left.candidate))
    });
    scored
        .into_iter()
        .take(count)
        .map(|scored| scored.candidate.to_owned())
        .collect()
}
