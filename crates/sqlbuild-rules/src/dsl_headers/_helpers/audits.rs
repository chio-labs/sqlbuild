//! Header audit lists split one item per line when a header line is too long.

use sqlbuild_core::text::main::python_isspace::python_isspace;

use crate::dsl_headers::_helpers::quoted::quoted_value_end;
use crate::dsl_headers::_helpers::text::{chars, contains, is_word, lstrip, slice, strip};
use crate::dsl_headers::constants::{AUDIT_WRAP_MAX_PASSES, AUDITS_KEYWORD, HEADER_INDENT, QUOTES};

/// One bracket group inside a header audit list.
struct Group {
    open: usize,
    close: usize,
    depth: usize,
    commas: Vec<usize>,
}

/// Whether `audits\s*[` matches at `start` after a word boundary.
fn audits_key_at(text: &[char], start: usize) -> bool {
    let keyword: Vec<char> = chars(AUDITS_KEYWORD);
    if (start > 0 && is_word(text[start - 1])) || !text[start..].starts_with(&keyword) {
        return false;
    }
    let mut index: usize = start + keyword.len();
    while index < text.len() && python_isspace(text[index]) {
        index += 1;
    }
    text.get(index) == Some(&'[')
}

/// Where `audits` would start for the bracket at `bracket`.
fn audits_key_start(text: &[char], bracket: usize) -> usize {
    let mut start: usize = bracket;
    while start > 0 && python_isspace(text[start - 1]) {
        start -= 1;
    }
    start.saturating_sub(AUDITS_KEYWORD.len())
}

/// Bracket groups at or inside each `audits [...]` value, outside quoted text.
fn audit_groups(text: &[char]) -> Vec<Group> {
    let mut groups: Vec<Group> = Vec::new();
    let mut open: Vec<(usize, char, Vec<usize>)> = Vec::new();
    let mut audit_depths: Vec<usize> = Vec::new();
    let mut index: usize = 0;
    while index < text.len() {
        let character: char = text[index];
        if QUOTES.contains(&character) {
            index = quoted_value_end(text, index);
            continue;
        }
        if character == '(' || character == '[' {
            if character == '[' && audits_key_at(text, audits_key_start(text, index)) {
                audit_depths.push(open.len());
            }
            open.push((index, if character == '(' { ')' } else { ']' }, Vec::new()));
        } else if open
            .last()
            .is_some_and(|(_, closer, _)| *closer == character)
        {
            if let Some((start, _, commas)) = open.pop() {
                if audit_depths
                    .last()
                    .is_some_and(|depth| open.len() >= *depth)
                {
                    groups.push(Group {
                        open: start,
                        close: index,
                        depth: open.len(),
                        commas,
                    });
                }
                if audit_depths.last() == Some(&open.len()) {
                    audit_depths.pop();
                }
            }
        } else if character == ','
            && let Some((_, _, commas)) = open.last_mut()
        {
            commas.push(index);
        }
        index += 1;
    }
    groups
}

fn explode(text: &[char], group: &Group, indent: &[char]) -> Vec<char> {
    let mut bounds: Vec<usize> = vec![group.open];
    bounds.extend(&group.commas);
    bounds.push(group.close);
    let inner: Vec<char> = [indent, &chars(HEADER_INDENT)].concat();
    let mut exploded: Vec<char> = text[..=group.open].to_vec();
    for pair in bounds.windows(2) {
        let item: &[char] = strip(slice(text, pair[0] + 1, pair[1]));
        if item.is_empty() {
            continue;
        }
        exploded.push('\n');
        exploded.extend(&inner);
        exploded.extend(item);
        exploded.push(',');
    }
    exploded.push('\n');
    exploded.extend(indent);
    exploded.extend(&text[group.close..]);
    exploded
}

fn explode_first_long_line(text: &[char], line_width: i64) -> Option<Vec<char>> {
    let groups: Vec<Group> = audit_groups(text);
    let width: usize = usize::try_from(line_width).unwrap_or(0);
    let mut line_start: usize = 0;
    for line in text.split(|character| *character == '\n') {
        let line_end: usize = line_start + line.len();
        if i64::try_from(line.len()).unwrap_or(i64::MAX) > line_width && !contains(line, "--") {
            let chosen: Option<&Group> = groups
                .iter()
                .filter(|group| {
                    line_start <= group.open
                        && group.close < line_end
                        && group.close - line_start >= width
                        && !strip(slice(text, group.open + 1, group.close)).is_empty()
                })
                .fold(None, |best: Option<&Group>, group| match best {
                    Some(best) if best.depth <= group.depth => Some(best),
                    _ => Some(group),
                });
            if let Some(group) = chosen {
                let indent: &[char] = &line[..line.len() - lstrip(line).len()];
                return Some(explode(text, group, indent));
            }
        }
        line_start = line_end + 1;
    }
    None
}

/// The header with its long audit-list lines exploded, repeated until none remain.
pub(crate) fn wrap_header(header_text: &[char], line_width: i64) -> Vec<char> {
    let mut text: Vec<char> = header_text.to_vec();
    for _ in 0..AUDIT_WRAP_MAX_PASSES {
        match explode_first_long_line(&text, line_width) {
            Some(exploded) => text = exploded,
            None => return text,
        }
    }
    text
}
