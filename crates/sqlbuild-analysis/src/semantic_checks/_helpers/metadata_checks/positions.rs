//! Python's `_text_position`: the first whole-word occurrence of a name, in code points.

use crate::semantic_checks::models::SemanticDeferral;

/// Python's `\w` for a character next to a match; beyond ASCII the two engines may disagree.
fn word_character(character: char) -> Result<bool, SemanticDeferral> {
    if character.is_ascii() {
        Ok(character.is_ascii_alphanumeric() || character == '_')
    } else {
        Err(SemanticDeferral::NonAsciiText)
    }
}

/// Python's `text.find(needle)` in code points, or None.
pub(crate) fn find_code_point(text: &str, needle: &str) -> Option<usize> {
    text.find(needle).map(|byte| text[..byte].chars().count())
}

/// Whether `characters[start..]` holds `name` at `position` as a whole word.
fn whole_word_at(
    characters: &[char],
    name: &[char],
    start: usize,
    position: usize,
) -> Result<bool, SemanticDeferral> {
    if characters[position..position + name.len()] != *name {
        return Ok(false);
    }
    if position > start && word_character(characters[position - 1])? {
        return Ok(false);
    }
    match characters.get(position + name.len()) {
        Some(next) => Ok(!word_character(*next)?),
        None => Ok(true),
    }
}

/// Python's `re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text[offset:])` start, or `offset`.
fn match_start(
    characters: &[char],
    name: &[char],
    offset: usize,
) -> Result<usize, SemanticDeferral> {
    let start: usize = offset.min(characters.len());
    if name.len() <= characters.len() - start {
        for position in start..=characters.len() - name.len() {
            if whole_word_at(characters, name, start, position)? {
                return Ok(position);
            }
        }
    }
    Ok(offset)
}

/// Python's `_text_position`: the 1-based line and column of `name` at or after `offset`.
pub(crate) fn text_position(
    text: &str,
    name: &str,
    offset: usize,
) -> Result<(i64, i64), SemanticDeferral> {
    let characters: Vec<char> = text.chars().collect();
    let name: Vec<char> = name.chars().collect();
    let start: usize = match_start(&characters, &name, offset)?;
    let before: &[char] = &characters[..start.min(characters.len())];
    let lines: usize = before
        .iter()
        .filter(|character| **character == '\n')
        .count();
    let last_newline: i64 = before
        .iter()
        .rposition(|character| *character == '\n')
        .map_or(-1, |index| i64::try_from(index).unwrap_or(i64::MAX));
    let start: i64 = i64::try_from(start).unwrap_or(i64::MAX);
    Ok((
        i64::try_from(lines).unwrap_or(i64::MAX) + 1,
        start - last_newline,
    ))
}
