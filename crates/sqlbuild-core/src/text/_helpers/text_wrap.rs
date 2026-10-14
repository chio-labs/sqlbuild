//! Python's `textwrap.wrap` with its default options.

use crate::text::constants::{MINIMUM_EM_DASH, TAB_SIZE};
use crate::text::main::is_decimal_digit::is_decimal_digit;
use crate::text::main::python_isalnum::python_isalnum;

/// `text.expandtabs()` with every remaining whitespace character replaced by a space.
fn munge_whitespace(text: &str) -> Vec<char> {
    let mut munged: Vec<char> = Vec::with_capacity(text.len());
    let mut column: usize = 0;
    for character in text.chars() {
        match character {
            '\t' => {
                let spaces: usize = TAB_SIZE - column % TAB_SIZE;
                munged.extend(std::iter::repeat_n(' ', spaces));
                column += spaces;
            }
            '\n' | '\r' => {
                munged.push(' ');
                column = 0;
            }
            '\x0b' | '\x0c' => {
                munged.push(' ');
                column += 1;
            }
            _ => {
                munged.push(character);
                column += 1;
            }
        }
    }
    munged
}

/// `textwrap.wrap(text, width, initial_indent=..., subsequent_indent=..., break_on_hyphens=...)`.
pub(crate) fn wrap(
    text: &str,
    width: usize,
    (initial, subsequent): (&str, &str),
    break_on_hyphens: bool,
) -> Vec<String> {
    let characters: Vec<char> = munge_whitespace(text);
    let mut chunks: Vec<Vec<char>> = if break_on_hyphens {
        split_chunks(&characters)
    } else {
        split_whitespace_chunks(&characters)
    };
    chunks.reverse();
    let mut lines: Vec<String> = Vec::new();
    while !chunks.is_empty() {
        let mut line: Vec<Vec<char>> = Vec::new();
        let mut length: usize = 0;
        let indent: &str = if lines.is_empty() {
            initial
        } else {
            subsequent
        };
        let available: i64 = width as i64 - indent.chars().count() as i64;
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
            let (head, rest) = split_long_word(
                chunk,
                (line.is_empty(), break_on_hyphens),
                length,
                available,
            );
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
    (line_is_empty, break_on_hyphens): (bool, bool),
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
    if break_on_hyphens
        && chunk.len() > space_left
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

/// `TextWrapper.wordsep_simple_re.split`: whitespace runs and the words between them.
fn split_whitespace_chunks(text: &[char]) -> Vec<Vec<char>> {
    let mut chunks: Vec<Vec<char>> = Vec::new();
    let mut start: usize = 0;
    while start < text.len() {
        let space: bool = is_space(text[start]);
        let length: usize = text[start..]
            .iter()
            .take_while(|character| is_space(**character) == space)
            .count();
        chunks.push(text[start..start + length].to_vec());
        start += length;
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
