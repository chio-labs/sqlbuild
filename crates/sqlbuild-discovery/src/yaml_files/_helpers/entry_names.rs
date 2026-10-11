//! The `\s*-\s*name:` entry prefix and every name `\s*(['"]?)<name>\1\s*(#.*)?$` accepts.

use std::collections::BTreeSet;

use sqlbuild_core::text::main::is_python_space::is_python_space;

const ENTRY_DASH: char = '-';
const NAME_KEY: &[char] = &['n', 'a', 'm', 'e', ':'];
const COMMENT_START: char = '#';
const QUOTES: [Option<char>; 3] = [None, Some('\''), Some('"')];

fn leading_whitespace(characters: &[char], start: usize) -> usize {
    let mut position: usize = start;
    while position < characters.len() && is_python_space(characters[position]) {
        position += 1;
    }
    position
}

/// `re.match(r"(?P<indent>\s*)-\s*name:", line)`: the indent and where the value starts.
pub(crate) fn entry_prefix(line: &[char]) -> Option<(usize, usize)> {
    let indent: usize = leading_whitespace(line, 0);
    if line.get(indent) != Some(&ENTRY_DASH) {
        return None;
    }
    let key_start: usize = leading_whitespace(line, indent + 1);
    line[key_start..]
        .starts_with(NAME_KEY)
        .then_some((indent, key_start + NAME_KEY.len()))
}

/// Positions after which only whitespace and an optional comment remain, in order.
fn closing_positions(value: &[char]) -> BTreeSet<usize> {
    let mut positions: BTreeSet<usize> = BTreeSet::new();
    let mut tail: Option<usize> = Some(value.len());
    while let Some(end) = tail {
        let mut position: usize = end;
        positions.insert(position);
        while position > 0 && is_python_space(value[position - 1]) {
            position -= 1;
            positions.insert(position);
        }
        tail = value[..end]
            .iter()
            .rposition(|character| *character == COMMENT_START);
    }
    positions
}

/// Whether `value[at..]` starts with the quote, where no quote always matches.
fn quoted_at(value: &[char], at: usize, quote: Option<char>) -> bool {
    quote.is_none_or(|quote| value.get(at) == Some(&quote))
}

/// Every name the entry value accepts, in Python's generation order.
pub(crate) fn entry_names(value: &[char]) -> Vec<String> {
    let closings: BTreeSet<usize> = closing_positions(value);
    let mut names: Vec<String> = Vec::new();
    for start in 0..=leading_whitespace(value, 0) {
        for quote in QUOTES {
            if !quoted_at(value, start, quote) {
                continue;
            }
            let width: usize = usize::from(quote.is_some());
            let body_start: usize = start + width;
            for closing in &closings {
                let Some(end) = closing.checked_sub(width) else {
                    continue;
                };
                if end >= body_start && quoted_at(value, end, quote) {
                    names.push(value[body_start..end].iter().collect());
                }
            }
        }
    }
    names
}
