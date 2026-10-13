//! Python `re` with `re.IGNORECASE` and `str.lower` for the refactoring string checks.

use sqlbuild_core::text::main::python_isalnum::python_isalnum;

use crate::string_literals::constants::{
    EXTRA_CASES, IDENTIFIER_PUNCTUATION, SQL_KEYWORDS, UNCASED_IN_PYTHON,
};

/// `re.search(r"\b(select|from|join|insert|update)\b", text, re.I) is not None`.
pub(crate) fn sql_like(text: &[char]) -> bool {
    let keywords: Vec<Vec<char>> = SQL_KEYWORDS
        .iter()
        .map(|keyword| keyword.chars().collect())
        .collect();
    (0..=text.len()).any(|start| word_boundary(text, start) && keyword_at(text, start, &keywords))
}

fn keyword_at(text: &[char], start: usize, keywords: &[Vec<char>]) -> bool {
    keywords.iter().any(|keyword| {
        matches_at(text, start, keyword) && word_boundary(text, start + keyword.len())
    })
}

/// `re.search(rf"(?<![A-Za-z0-9_$]){re.escape(word)}(?![A-Za-z0-9_$])", text, re.I) is not None`.
pub(crate) fn has_word(text: &[char], word: &str) -> bool {
    let word: Vec<char> = word.chars().collect();
    if word.len() > text.len() {
        return false;
    }
    (0..=text.len() - word.len()).any(|start| {
        let end: usize = start + word.len();
        (start == 0 || !identifier_character(text[start - 1]))
            && matches_at(text, start, &word)
            && text
                .get(end)
                .is_none_or(|next| !identifier_character(*next))
    })
}

/// Python's `text.lower()`, keeping code points CPython 3.12 does not case-map.
pub(crate) fn python_lower(text: &str) -> String {
    let mut lowered: String = String::with_capacity(text.len());
    let mut segment_start: usize = 0;
    for (index, character) in text.char_indices() {
        if uncased_in_python(character) {
            lowered.push_str(&text[segment_start..index].to_lowercase());
            lowered.push(character);
            segment_start = index + character.len_utf8();
        }
    }
    lowered.push_str(&text[segment_start..].to_lowercase());
    lowered
}

fn matches_at(text: &[char], start: usize, pattern: &[char]) -> bool {
    pattern.iter().enumerate().all(|(offset, expected)| {
        text.get(start + offset)
            .is_some_and(|found| literal_matches(*expected, *found))
    })
}

/// Python's `\b` for `str` patterns: a word character on exactly one side.
fn word_boundary(text: &[char], at: usize) -> bool {
    let before: bool = at > 0
        && text
            .get(at - 1)
            .is_some_and(|character| word_character(*character));
    let after: bool = text
        .get(at)
        .is_some_and(|character| word_character(*character));
    before != after
}

fn word_character(character: char) -> bool {
    character == '_' || python_isalnum(character)
}

/// `[A-Za-z0-9_$]` under `re.IGNORECASE`: the folded character is in the folded class.
fn identifier_character(character: char) -> bool {
    let folded: char = sre_lower(character);
    identifier_base(folded)
        || EXTRA_CASES.iter().any(|(code, extras)| {
            char::from_u32(*code).is_some_and(identifier_base)
                && extras.contains(&u32::from(folded))
        })
}

fn identifier_base(character: char) -> bool {
    character.is_ascii_lowercase()
        || character.is_ascii_digit()
        || IDENTIFIER_PUNCTUATION.contains(&character)
}

/// One pattern literal against one character under `re.IGNORECASE`, as `sre` compiles it.
fn literal_matches(pattern: char, character: char) -> bool {
    if !sre_cased(pattern) {
        return character == pattern;
    }
    let lower: char = sre_lower(pattern);
    let folded: char = sre_lower(character);
    folded == lower || extra_cases(lower).contains(&u32::from(folded))
}

fn extra_cases(lower: char) -> &'static [u32] {
    EXTRA_CASES
        .binary_search_by_key(&u32::from(lower), |(code, _)| *code)
        .map_or(&[], |index| EXTRA_CASES[index].1)
}

fn uncased_in_python(character: char) -> bool {
    let code: u32 = u32::from(character);
    UNCASED_IN_PYTHON
        .iter()
        .any(|(first, last)| (*first..=*last).contains(&code))
}

/// `_sre.unicode_tolower`: the first code point of the full lowercase mapping.
fn sre_lower(character: char) -> char {
    if uncased_in_python(character) {
        return character;
    }
    character.to_lowercase().next().unwrap_or(character)
}

/// `_sre.unicode_iscased`: the first code point of either case mapping differs.
fn sre_cased(character: char) -> bool {
    if uncased_in_python(character) {
        return false;
    }
    sre_lower(character) != character
        || character.to_uppercase().next().unwrap_or(character) != character
}
