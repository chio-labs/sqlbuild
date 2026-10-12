//! Spelling suggestions ranked by edit-distance similarity, counting adjacent swaps as one edit.

/// The optimal-string-alignment distance: edits and adjacent swaps between two words.
fn edit_distance(left: &[char], right: &[char]) -> usize {
    let width: usize = right.len() + 1;
    let mut rows: [Vec<usize>; 3] = [vec![0; width], vec![0; width], (0..width).collect()];
    for row in 1..=left.len() {
        rows.rotate_left(1);
        rows[2][0] = row;
        for column in 1..width {
            let cost: usize = usize::from(left[row - 1] != right[column - 1]);
            let mut best: usize = (rows[1][column - 1] + cost)
                .min(rows[1][column] + 1)
                .min(rows[2][column - 1] + 1);
            if row > 1
                && column > 1
                && left[row - 1] == right[column - 2]
                && left[row - 2] == right[column - 1]
            {
                best = best.min(rows[0][column - 2] + 1);
            }
            rows[2][column] = best;
        }
    }
    rows[2][right.len()]
}

/// Similarity from 0 to 1: one minus the edit distance over the longer word's length.
fn similarity(word: &[char], candidate: &[char]) -> f64 {
    let longest: usize = word.len().max(candidate.len());
    if longest == 0 {
        return 1.0;
    }
    1.0 - edit_distance(word, candidate) as f64 / longest as f64
}

/// The best `count` candidates whose similarity to `word` reaches `cutoff`, best first.
pub fn close_matches(word: &str, possibilities: &[&str], count: usize, cutoff: f64) -> Vec<String> {
    let word: Vec<char> = word.chars().collect();
    let mut scored: Vec<(f64, &str)> = possibilities
        .iter()
        .map(|candidate| {
            (
                similarity(&word, &candidate.chars().collect::<Vec<char>>()),
                *candidate,
            )
        })
        .filter(|(score, _)| *score >= cutoff)
        .collect();
    scored.sort_by(|left, right| right.0.total_cmp(&left.0).then_with(|| left.1.cmp(right.1)));
    scored
        .into_iter()
        .take(count)
        .map(|(_, candidate)| candidate.to_owned())
        .collect()
}
