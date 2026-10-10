//! Python's `fnmatch.fnmatchcase`, translated the way `fnmatch._translate` does.

use regex::Regex;

/// One translated pattern piece; `Never` is Python's `(?!)` for an empty set.
enum Piece {
    Text(String),
    Never,
}

pub(crate) fn fnmatch(pattern: &str, name: &str) -> bool {
    let mut translated: String = String::from("(?s)^(?:");
    for piece in translate(&pattern.chars().collect::<Vec<char>>()) {
        match piece {
            Piece::Text(text) => translated.push_str(&text),
            Piece::Never => return false,
        }
    }
    translated.push_str(")$");
    let Ok(expression) = Regex::new(&translated) else {
        return false;
    };
    expression.is_match(name)
}

fn translate(pattern: &[char]) -> Vec<Piece> {
    let mut pieces: Vec<Piece> = Vec::new();
    let mut previous_star: bool = false;
    let mut index: usize = 0;
    while index < pattern.len() {
        let character: char = pattern[index];
        index += 1;
        let star: bool = character == '*';
        match character {
            '*' if previous_star => {}
            '*' => pieces.push(Piece::Text(".*".to_owned())),
            '?' => pieces.push(Piece::Text(".".to_owned())),
            '[' => {
                let (piece, next) = set(pattern, index);
                pieces.push(piece);
                index = next;
            }
            _ => pieces.push(Piece::Text(regex::escape(&character.to_string()))),
        }
        previous_star = star;
    }
    pieces
}

/// The set starting after `[` at `start`, and the index after it; an unclosed `[` is literal.
fn set(pattern: &[char], start: usize) -> (Piece, usize) {
    let length: usize = pattern.len();
    let mut end: usize = start;
    if end < length && pattern[end] == '!' {
        end += 1;
    }
    if end < length && pattern[end] == ']' {
        end += 1;
    }
    while end < length && pattern[end] != ']' {
        end += 1;
    }
    if end >= length {
        return (Piece::Text("\\[".to_owned()), start);
    }
    let stuff: Vec<char> = pattern[start..end].to_vec();
    let body: String = if stuff.contains(&'-') {
        ranges(pattern, start, end)
    } else {
        stuff.iter().map(|&character| escaped(character)).collect()
    };
    let piece: Piece = match body.as_str() {
        "" => Piece::Never,
        "!" => Piece::Text(".".to_owned()),
        _ => match body.strip_prefix('!') {
            Some(negated) => Piece::Text(format!("[^{negated}]")),
            None => Piece::Text(format!("[{body}]")),
        },
    };
    (piece, end + 1)
}

/// Python's chunking of a set with hyphens, dropping empty ranges, joined with range hyphens.
fn ranges(pattern: &[char], start: usize, end: usize) -> String {
    let mut chunks: Vec<Vec<char>> = Vec::new();
    let mut chunk_start: usize = start;
    let mut search: usize = if pattern[start] == '!' {
        start + 2
    } else {
        start + 1
    };
    while let Some(found) = (search..end).find(|&position| pattern[position] == '-') {
        chunks.push(pattern[chunk_start..found].to_vec());
        chunk_start = found + 1;
        search = found + 3;
    }
    let last: Vec<char> = pattern[chunk_start..end].to_vec();
    match (last.is_empty(), chunks.last_mut()) {
        (true, Some(previous)) => previous.push('-'),
        _ => chunks.push(last),
    }
    let mut position: usize = chunks.len().saturating_sub(1);
    while position > 0 {
        let (left, right) = chunks.split_at_mut(position);
        let previous: &mut Vec<char> = &mut left[position - 1];
        if let (Some(&high), Some(&low)) = (previous.last(), right[0].first())
            && high > low
        {
            previous.pop();
            previous.extend(right[0].iter().skip(1));
            chunks.remove(position);
        }
        position -= 1;
    }
    chunks
        .iter()
        .map(|chunk| {
            chunk
                .iter()
                .map(|&character| escaped(character))
                .collect::<String>()
        })
        .collect::<Vec<String>>()
        .join("-")
}

/// A literal set member; `!` stays bare so a leading one still negates, as in Python.
fn escaped(character: char) -> String {
    match character {
        '!' => "!".to_owned(),
        '\\' | '-' | '&' | '~' | '|' | '[' | ']' | '^' => format!("\\{character}"),
        _ => character.to_string(),
    }
}
