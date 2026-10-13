//! Python's `textwrap.wrap` with its default options, as `argparse` uses it.

use sqlbuild_core::text::main::is_decimal_digit::is_decimal_digit;
use sqlbuild_core::text::main::python_isalnum::python_isalnum;

use crate::argv::constants::MINIMUM_EM_DASH;

/// `_whitespace_matcher.sub(' ', text).strip()`: ASCII whitespace runs become one space.
pub(crate) fn normalize_whitespace(text: &str) -> String {
    let mut normalized: String = String::with_capacity(text.len());
    let mut in_space: bool = false;
    for character in text.chars() {
        if matches!(character, ' ' | '\t' | '\n' | '\r' | '\x0b' | '\x0c') {
            in_space = true;
            continue;
        }
        if in_space && !normalized.is_empty() {
            normalized.push(' ');
        }
        in_space = false;
        normalized.push(character);
    }
    normalized
}

/// `textwrap.wrap(text, width, initial_indent=indent, subsequent_indent=indent)`.
pub(crate) fn wrap(text: &str, width: usize, indent: &str) -> Vec<String> {
    let characters: Vec<char> = text.chars().collect();
    let mut chunks: Vec<Vec<char>> = split_chunks(&characters);
    chunks.reverse();
    let indent_length: usize = indent.chars().count();
    let mut lines: Vec<String> = Vec::new();
    while !chunks.is_empty() {
        let mut line: Vec<Vec<char>> = Vec::new();
        let mut length: usize = 0;
        let available: i64 = width as i64 - indent_length as i64;
        if !lines.is_empty() && chunks.last().is_some_and(|chunk| is_blank(chunk)) {
            chunks.pop();
        }
        while let Some(chunk) = chunks.last() {
            if (length + chunk.len()) as i64 <= available {
                length += chunk.len();
                line.push(chunks.pop().unwrap_or_default());
            } else {
                break;
            }
        }
        if let Some(chunk) = chunks.pop_if(|chunk| chunk.len() as i64 > available) {
            let (head, rest) = split_long_word(chunk, line.is_empty(), length, available);
            line.extend(head);
            chunks.extend(rest);
        }
        if line.last().is_some_and(|chunk| is_blank(chunk)) {
            line.pop();
        }
        if !line.is_empty() {
            let joined: String = line.iter().flatten().collect();
            lines.push(format!("{indent}{joined}"));
        }
    }
    lines
}

/// `_handle_long_word`: the part of a too-long chunk the line takes, and what stays queued.
fn split_long_word(
    mut chunk: Vec<char>,
    line_is_empty: bool,
    length: usize,
    width: i64,
) -> (Option<Vec<char>>, Option<Vec<char>>) {
    let space_left: i64 = if width < 1 { 1 } else { width - length as i64 };
    if space_left <= 0 {
        return if line_is_empty {
            (Some(chunk), None)
        } else {
            (None, Some(chunk))
        };
    }
    let space_left: usize = space_left as usize;
    let mut end: usize = space_left.min(chunk.len());
    if chunk.len() > space_left
        && let Some(hyphen) = chunk[..space_left]
            .iter()
            .rposition(|character| *character == '-')
        && hyphen > 0
        && chunk[..hyphen].iter().any(|character| *character != '-')
    {
        end = hyphen + 1;
    }
    let rest: Vec<char> = chunk.split_off(end);
    (Some(chunk), Some(rest))
}

fn is_blank(chunk: &[char]) -> bool {
    chunk.iter().all(|character| character.is_whitespace())
}

fn is_space(character: char) -> bool {
    matches!(character, '\t' | '\n' | '\x0b' | '\x0c' | '\r' | ' ')
}

fn is_word(character: char) -> bool {
    character == '_' || python_isalnum(character)
}

fn is_word_punct(character: char) -> bool {
    is_word(character) || matches!(character, '!' | '"' | '\'' | '&' | '.' | ',' | '?')
}

fn is_letter(character: char) -> bool {
    is_word(character) && !is_decimal_digit(character)
}

/// `TextWrapper.wordsep_re.split`: whitespace runs, em-dashes and possibly hyphenated words.
fn split_chunks(text: &[char]) -> Vec<Vec<char>> {
    let mut chunks: Vec<Vec<char>> = Vec::new();
    let mut start: usize = 0;
    while start < text.len() {
        let end: usize = chunk_end(text, start);
        chunks.push(text[start..end].to_vec());
        start = end;
    }
    chunks
}

fn at(text: &[char], index: usize) -> Option<char> {
    text.get(index).copied()
}

fn letter_at(text: &[char], index: Option<usize>) -> bool {
    index
        .and_then(|index| at(text, index))
        .is_some_and(is_letter)
}

/// The end of a `-{2,}(?=\w)` match at `start`, if there is one.
fn em_dash_end(text: &[char], start: usize) -> Option<usize> {
    let count: usize = text[start..]
        .iter()
        .take_while(|character| **character == '-')
        .count();
    (count >= MINIMUM_EM_DASH && at(text, start + count).is_some_and(is_word))
        .then_some(start + count)
}

fn chunk_end(text: &[char], start: usize) -> usize {
    if is_space(text[start]) {
        return start
            + text[start..]
                .iter()
                .take_while(|character| is_space(**character))
                .count();
    }
    if start > 0
        && is_word_punct(text[start - 1])
        && let Some(end) = em_dash_end(text, start)
    {
        return end;
    }
    let mut position: usize = start + 1;
    loop {
        if at(text, position) == Some('-') {
            let two_letters: bool = letter_at(text, position.checked_sub(2))
                && letter_at(text, position.checked_sub(1));
            let letter_hyphen_letter: bool = letter_at(text, position.checked_sub(3))
                && at(text, position.wrapping_sub(2)) == Some('-')
                && letter_at(text, position.checked_sub(1));
            let ahead: bool = letter_at(text, Some(position + 1))
                && (letter_at(text, Some(position + 2))
                    || (at(text, position + 2) == Some('-')
                        && letter_at(text, Some(position + 3))));
            if (two_letters || letter_hyphen_letter) && ahead {
                return position + 1;
            }
        }
        match at(text, position) {
            None => return position,
            Some(character) if is_space(character) => return position,
            Some(_) => {}
        }
        if is_word_punct(text[position - 1]) && em_dash_end(text, position).is_some() {
            return position;
        }
        position += 1;
    }
}
