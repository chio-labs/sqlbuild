//! Quoted identifier spans in a relation name.

/// The end of a doubled-escape quoted identifier opening at `start`, as a backtracking regex finds it.
fn quoted_end(chars: &[char], start: usize) -> Option<usize> {
    let close: char = match chars[start] {
        '"' => '"',
        '`' => '`',
        '[' => ']',
        _ => return None,
    };
    let mut position: usize = start + 1;
    let mut last_pair: Option<usize> = None;
    while position < chars.len() {
        if chars[position] != close {
            position += 1;
            continue;
        }
        if chars.get(position + 1) == Some(&close) {
            last_pair = Some(position);
            position += 2;
            continue;
        }
        return Some(position + 1);
    }
    last_pair.map(|pair| pair + 1)
}

/// The relation split into `(text, quoted)` segments in order.
fn quoted_segments(relation: &str) -> Vec<(String, bool)> {
    let chars: Vec<char> = relation.chars().collect();
    let mut segments: Vec<(String, bool)> = Vec::new();
    let mut plain: String = String::new();
    let mut position: usize = 0;
    while position < chars.len() {
        match quoted_end(&chars, position) {
            Some(end) => {
                segments.push((std::mem::take(&mut plain), false));
                segments.push((chars[position..end].iter().collect(), true));
                position = end;
            }
            None => {
                plain.push(chars[position]);
                position += 1;
            }
        }
    }
    segments.push((plain, false));
    segments
}

/// Lowercase ordinary identifiers while preserving quoted identifier case.
pub(crate) fn clone_relation_display_name(relation: &str) -> String {
    quoted_segments(relation)
        .into_iter()
        .map(|(text, quoted)| if quoted { text } else { text.to_lowercase() })
        .collect()
}
