//! `difflib.SequenceMatcher` ratios over code points, with `autojunk` and no junk function.

use std::collections::HashMap;

const AUTOJUNK_MIN_LENGTH: usize = 200;

/// One candidate and its `SequenceMatcher.ratio()` against the word.
pub(crate) struct ScoredCandidate<'candidate> {
    pub(crate) score: f64,
    pub(crate) candidate: &'candidate str,
}

/// `SequenceMatcher.b2j` of the word, without the popular elements `autojunk` removes.
struct TargetIndex {
    positions: HashMap<char, Vec<usize>>,
}

/// Half-open ranges of the candidate and the word that one longest-match search covers.
#[derive(Clone, Copy)]
struct SearchWindow {
    source: (usize, usize),
    target: (usize, usize),
}

/// The candidates `get_close_matches` keeps, scored, in input order.
pub(crate) fn scored_candidates<'candidate>(
    word: &str,
    possibilities: &[&'candidate str],
    cutoff: f64,
) -> Vec<ScoredCandidate<'candidate>> {
    let target: Vec<char> = word.chars().collect();
    let index: TargetIndex = target_index(&target);
    let mut scored: Vec<ScoredCandidate<'candidate>> = Vec::new();
    for candidate in possibilities {
        let source: Vec<char> = candidate.chars().collect();
        if real_quick_ratio(&source, &target) >= cutoff
            && quick_ratio(&source, &target) >= cutoff
            && ratio(&source, &target, &index) >= cutoff
        {
            scored.push(ScoredCandidate {
                score: ratio(&source, &target, &index),
                candidate,
            });
        }
    }
    scored
}

fn target_index(target: &[char]) -> TargetIndex {
    let mut positions: HashMap<char, Vec<usize>> = HashMap::new();
    for (index, character) in target.iter().enumerate() {
        positions.entry(*character).or_default().push(index);
    }
    if target.len() >= AUTOJUNK_MIN_LENGTH {
        let threshold: usize = target.len() / 100 + 1;
        positions.retain(|_, indexes| indexes.len() <= threshold);
    }
    TargetIndex { positions }
}

fn calculate_ratio(matches: usize, length: usize) -> f64 {
    if length == 0 {
        return 1.0;
    }
    2.0 * matches as f64 / length as f64
}

fn real_quick_ratio(source: &[char], target: &[char]) -> f64 {
    calculate_ratio(source.len().min(target.len()), source.len() + target.len())
}

fn quick_ratio(source: &[char], target: &[char]) -> f64 {
    let mut available: HashMap<char, isize> = HashMap::new();
    for character in target {
        *available.entry(*character).or_default() += 1;
    }
    let mut matches: usize = 0;
    for character in source {
        if let Some(count) = available.get_mut(character) {
            if *count > 0 {
                matches += 1;
            }
            *count -= 1;
        }
    }
    calculate_ratio(matches, source.len() + target.len())
}

fn ratio(source: &[char], target: &[char], index: &TargetIndex) -> f64 {
    let matches: usize = matching_block_sizes(source, target, index);
    calculate_ratio(matches, source.len() + target.len())
}

fn matching_block_sizes(source: &[char], target: &[char], index: &TargetIndex) -> usize {
    let mut total: usize = 0;
    let mut queue: Vec<SearchWindow> = vec![SearchWindow {
        source: (0, source.len()),
        target: (0, target.len()),
    }];
    while let Some(window) = queue.pop() {
        let (start, target_start, size) = find_longest_match(source, target, index, window);
        if size == 0 {
            continue;
        }
        total += size;
        if window.source.0 < start && window.target.0 < target_start {
            queue.push(SearchWindow {
                source: (window.source.0, start),
                target: (window.target.0, target_start),
            });
        }
        if start + size < window.source.1 && target_start + size < window.target.1 {
            queue.push(SearchWindow {
                source: (start + size, window.source.1),
                target: (target_start + size, window.target.1),
            });
        }
    }
    total
}

fn find_longest_match(
    source: &[char],
    target: &[char],
    index: &TargetIndex,
    window: SearchWindow,
) -> (usize, usize, usize) {
    let (source_low, source_high) = window.source;
    let (target_low, target_high) = window.target;
    let (mut best_source, mut best_target, mut best_size) = (source_low, target_low, 0);
    let mut lengths: HashMap<usize, usize> = HashMap::new();
    for (position, character) in source.iter().enumerate().take(source_high).skip(source_low) {
        let mut next_lengths: HashMap<usize, usize> = HashMap::new();
        for &target_position in index.positions.get(character).into_iter().flatten() {
            if target_position < target_low {
                continue;
            }
            if target_position >= target_high {
                break;
            }
            let length: usize = target_position
                .checked_sub(1)
                .and_then(|previous| lengths.get(&previous))
                .copied()
                .unwrap_or(0)
                + 1;
            next_lengths.insert(target_position, length);
            if length > best_size {
                best_source = position + 1 - length;
                best_target = target_position + 1 - length;
                best_size = length;
            }
        }
        lengths = next_lengths;
    }
    while best_source > source_low
        && best_target > target_low
        && source[best_source - 1] == target[best_target - 1]
    {
        best_source -= 1;
        best_target -= 1;
        best_size += 1;
    }
    while best_source + best_size < source_high
        && best_target + best_size < target_high
        && source[best_source + best_size] == target[best_target + best_size]
    {
        best_size += 1;
    }
    (best_source, best_target, best_size)
}
