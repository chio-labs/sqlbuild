//! Python's `difflib.get_close_matches` over characters, for selector name suggestions.

use std::collections::HashMap;

use crate::graph::constants::{AUTOJUNK_DIVISOR, AUTOJUNK_MIN_LENGTH};

/// `difflib.SequenceMatcher(None, a, word)` state for one fixed `word`.
struct Matcher<'word> {
    word: &'word [char],
    positions: HashMap<char, Vec<usize>>,
}

impl<'word> Matcher<'word> {
    fn new(word: &'word [char]) -> Self {
        let mut positions: HashMap<char, Vec<usize>> = HashMap::new();
        for (index, character) in word.iter().enumerate() {
            positions.entry(*character).or_default().push(index);
        }
        if word.len() >= AUTOJUNK_MIN_LENGTH {
            let limit: usize = word.len() / AUTOJUNK_DIVISOR + 1;
            positions.retain(|_, indexes| indexes.len() <= limit);
        }
        Self { word, positions }
    }

    /// `find_longest_match` with no junk: `(start in a, start in word, size)`.
    fn longest(&self, a: &[char], bounds: (usize, usize, usize, usize)) -> (usize, usize, usize) {
        let (a_low, a_high, b_low, b_high) = bounds;
        let (mut best_a, mut best_b, mut best_size) = (a_low, b_low, 0);
        let mut lengths: HashMap<usize, usize> = HashMap::new();
        for (offset, character) in a[a_low..a_high].iter().enumerate() {
            let index: usize = a_low + offset;
            let mut next: HashMap<usize, usize> = HashMap::new();
            for &position in self.positions.get(character).map_or(&[][..], Vec::as_slice) {
                if position < b_low {
                    continue;
                }
                if position >= b_high {
                    break;
                }
                let previous: usize = position
                    .checked_sub(1)
                    .and_then(|before| lengths.get(&before).copied())
                    .unwrap_or(0);
                let size: usize = previous + 1;
                next.insert(position, size);
                if size > best_size {
                    (best_a, best_b, best_size) = (index + 1 - size, position + 1 - size, size);
                }
            }
            lengths = next;
        }
        while best_a > a_low && best_b > b_low && a[best_a - 1] == self.word[best_b - 1] {
            (best_a, best_b, best_size) = (best_a - 1, best_b - 1, best_size + 1);
        }
        while best_a + best_size < a_high
            && best_b + best_size < b_high
            && a[best_a + best_size] == self.word[best_b + best_size]
        {
            best_size += 1;
        }
        (best_a, best_b, best_size)
    }

    /// The total size of `get_matching_blocks`.
    fn matched(&self, a: &[char]) -> usize {
        let mut total: usize = 0;
        let mut pending: Vec<(usize, usize, usize, usize)> = vec![(0, a.len(), 0, self.word.len())];
        while let Some(bounds) = pending.pop() {
            let (a_low, a_high, b_low, b_high) = bounds;
            let (start_a, start_b, size) = self.longest(a, bounds);
            if size == 0 {
                continue;
            }
            total += size;
            if a_low < start_a && b_low < start_b {
                pending.push((a_low, start_a, b_low, start_b));
            }
            if start_a + size < a_high && start_b + size < b_high {
                pending.push((start_a + size, a_high, start_b + size, b_high));
            }
        }
        total
    }

    fn ratio(&self, a: &[char]) -> f64 {
        let length: usize = a.len() + self.word.len();
        if length == 0 {
            return 1.0;
        }
        2.0 * self.matched(a) as f64 / length as f64
    }
}

/// The best `limit` candidates scoring at least `cutoff`, best first, as Python orders them.
pub(crate) fn close_matches(
    word: &str,
    candidates: &[&str],
    limit: usize,
    cutoff: f64,
) -> Vec<String> {
    let word: Vec<char> = word.chars().collect();
    let matcher: Matcher<'_> = Matcher::new(&word);
    let mut scored: Vec<(f64, &str)> = candidates
        .iter()
        .map(|candidate| {
            let characters: Vec<char> = candidate.chars().collect();
            (matcher.ratio(&characters), *candidate)
        })
        .filter(|(score, _)| *score >= cutoff)
        .collect();
    scored.sort_by(|left, right| right.0.total_cmp(&left.0).then_with(|| right.1.cmp(left.1)));
    scored
        .into_iter()
        .take(limit)
        .map(|(_, candidate)| candidate.to_owned())
        .collect()
}
