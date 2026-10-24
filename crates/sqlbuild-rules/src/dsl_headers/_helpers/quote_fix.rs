//! Header descriptions that escape or double their double quotes, and their `"""` rewrites.

use sqlbuild_core::text::main::python_isspace::python_isspace;
use sqlbuild_sqltext::header_strings::constants::{LONGEST_CLOSING_RUN, TRIPLE_QUOTE};
use sqlbuild_sqltext::header_strings::main::closes_inside_text::closes_inside_text;
use sqlbuild_sqltext::header_strings::main::fold_prose::fold_prose;
use sqlbuild_sqltext::header_strings::main::header_quoted_end::header_quoted_end;
use sqlbuild_sqltext::header_strings::main::opens_triple_quote::opens_triple_quote;
use sqlbuild_sqltext::header_strings::main::prose_end::prose_end;
use sqlbuild_sqltext::header_strings::main::prose_string::prose_string;

use crate::dsl_headers::_helpers::text::{chars, is_word};
use crate::dsl_headers::constants::{DESCRIPTION_KEY, QUOTES};
use crate::dsl_headers::models::HeaderSpan;

/// The end of the `"..."` string at `start` read with `\"` and `""` as quotes in the text.
fn escaped_end(text: &[char], start: usize) -> Option<usize> {
    let mut index: usize = start + 1;
    while index < text.len() {
        let pair: bool = matches!(text[index], '\\' | '"') && text.get(index + 1) == Some(&'"');
        if pair {
            index += 2;
            continue;
        }
        if text[index] == '"' {
            return Some(index + 1);
        }
        index += 1;
    }
    None
}

/// The inside of a `"..."` string with `\"` and `""` as real quotes, if it has one and no `\`.
fn unescaped(raw: &[char]) -> Option<String> {
    let mut text: String = String::with_capacity(raw.len());
    let mut escaped: bool = false;
    let mut index: usize = 0;
    while index < raw.len() {
        let pair: bool = matches!(raw[index], '\\' | '"') && raw.get(index + 1) == Some(&'"');
        if pair {
            escaped = true;
            text.push('"');
            index += 2;
            continue;
        }
        if raw[index] == '\\' {
            return None;
        }
        text.push(raw[index]);
        index += 1;
    }
    escaped.then_some(text)
}

/// `"""text"""` when it stores the same folded text and closes where it should.
fn triple_quoted(text: &str, after: &[char]) -> Option<Vec<char>> {
    let trailing: usize = text.chars().rev().take_while(|unit| *unit == '"').count();
    if text.contains(TRIPLE_QUOTE) || trailing + TRIPLE_QUOTE.len() > LONGEST_CLOSING_RUN {
        return None;
    }
    let rewritten: Vec<char> = chars(&format!("{TRIPLE_QUOTE}{text}{TRIPLE_QUOTE}"));
    let Ok(prose) = prose_string(&rewritten, 0) else {
        return None;
    };
    let followed: Vec<char> = [rewritten.as_slice(), after].concat();
    (prose.end == rewritten.len()
        && prose.value == fold_prose(text)
        && !closes_inside_text(&followed, rewritten.len()))
    .then_some(rewritten)
}

/// The `description` string spans of one header that escape or double a quote, and rewrites.
pub(crate) fn header_fixes(text: &[char], header: &HeaderSpan) -> Vec<(usize, usize, Vec<char>)> {
    let mut fixes: Vec<(usize, usize, Vec<char>)> = Vec::new();
    let key: Vec<char> = chars(DESCRIPTION_KEY);
    let mut index: usize = header.start;
    while index < header.end {
        if QUOTES.contains(&text[index]) {
            index = header_quoted_end(&text[..header.end], index).unwrap_or(header.end);
            continue;
        }
        let at_key: bool = text[index..header.end].starts_with(&key)
            && !(index > 0 && is_word(text[index - 1]))
            && !text
                .get(index + key.len())
                .is_some_and(|next| is_word(*next));
        if !at_key {
            index += 1;
            continue;
        }
        let mut start: usize = index + key.len();
        while start < header.end && python_isspace(text[start]) {
            start += 1;
        }
        index = start;
        if text.get(start) != Some(&'"') || opens_triple_quote(text, start) {
            continue;
        }
        let bounded: &[char] = &text[..header.end];
        if let Ok(end) = prose_end(bounded, start) {
            index = end;
            continue;
        }
        let Some(end) = escaped_end(bounded, start) else {
            continue;
        };
        let rewrite: Option<Vec<char>> = unescaped(&text[start + 1..end - 1])
            .and_then(|unquoted| triple_quoted(&unquoted, &text[end..header.end]));
        if let Some(rewrite) = rewrite {
            fixes.push((start, end, rewrite));
        }
        index = end;
    }
    fixes
}
