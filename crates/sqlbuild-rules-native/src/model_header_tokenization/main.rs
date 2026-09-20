//! Batched tokenization for authored SQLBuild MODEL headers.

use rayon::prelude::*;
use rayon::{ThreadPool, ThreadPoolBuilder};

pub(crate) const MAX_TOKENIZER_WORKERS: usize = 4;
pub(crate) const TOKENIZER_WORKER_STACK_BYTES: usize = 16 * 1024 * 1024;

pub(crate) const END_TOKEN: u8 = 0;
pub(crate) const WORD_TOKEN: u8 = 1;
pub(crate) const STRING_TOKEN: u8 = 2;
pub(crate) const SYMBOL_TOKEN: u8 = 3;

pub(crate) type HeaderToken = (u8, String, usize);
pub(crate) type HeaderTokenization = (Option<Vec<HeaderToken>>, Option<String>);

pub(crate) fn tokenize_batch(headers: &[String]) -> Result<Vec<HeaderTokenization>, String> {
    let pool = build_tokenizer_pool(headers.len())?;
    Ok(pool.install(|| {
        headers
            .par_iter()
            .map(|header| match tokenize(header) {
                Ok(tokens) => (Some(tokens), None),
                Err(error) => (None, Some(error)),
            })
            .collect()
    }))
}

pub(crate) fn build_tokenizer_pool(header_count: usize) -> Result<ThreadPool, String> {
    ThreadPoolBuilder::new()
        .num_threads(header_count.clamp(1, MAX_TOKENIZER_WORKERS))
        .stack_size(TOKENIZER_WORKER_STACK_BYTES)
        .build()
        .map_err(|error| error.to_string())
}

fn tokenize(header: &str) -> Result<Vec<HeaderToken>, String> {
    let characters: Vec<char> = header.chars().collect();
    let mut tokens = Vec::new();
    let mut index = 0;
    while index < characters.len() {
        let character = characters[index];
        if is_python_whitespace(character) {
            index += 1;
            continue;
        }
        if starts_template(&characters, index) {
            let template_end = find_character(&characters, '}', index + 2)
                .ok_or_else(|| format!("unterminated template value at position {index}"))?;
            tokens.push((
                WORD_TOKEN,
                characters[index..=template_end].iter().collect(),
                index,
            ));
            index = template_end + 1;
            continue;
        }
        if is_symbol(character) || character == ':' {
            tokens.push((SYMBOL_TOKEN, character.to_string(), index));
            index += 1;
            continue;
        }
        if matches!(character, '\'' | '"') {
            let (value, next_index) = read_quoted_string(&characters, index)?;
            tokens.push((STRING_TOKEN, value, index));
            index = next_index;
            continue;
        }

        let start = index;
        while index < characters.len() {
            if starts_template(&characters, index) {
                let template_end = find_character(&characters, '}', index + 2)
                    .ok_or_else(|| format!("unterminated template value at position {index}"))?;
                index = template_end + 1;
                continue;
            }
            let next = characters[index];
            if is_python_whitespace(next) || is_symbol(next) || next == ':' {
                break;
            }
            if matches!(next, '\'' | '"') {
                let quote_name = if next == '\'' { "single" } else { "double" };
                return Err(format!(
                    "unexpected {quote_name} quote inside bare value at position {index}; quote the whole value"
                ));
            }
            index += 1;
        }
        if start == index {
            return Err(format!(
                "unexpected character '{character}' at position {start}"
            ));
        }
        tokens.push((WORD_TOKEN, characters[start..index].iter().collect(), start));
    }
    tokens.push((END_TOKEN, String::new(), characters.len()));
    Ok(tokens)
}

fn read_quoted_string(characters: &[char], start: usize) -> Result<(String, usize), String> {
    let quote = characters[start];
    let quote_name = if quote == '\'' { "single" } else { "double" };
    let mut value = String::new();
    let mut index = start + 1;
    while index < characters.len() {
        let character = characters[index];
        if character == '\\' {
            if index + 1 >= characters.len() {
                return Err(format!("unterminated escape at position {index}"));
            }
            value.push(characters[index + 1]);
            index += 2;
            continue;
        }
        if character == quote {
            return Ok((value, index + 1));
        }
        value.push(character);
        index += 1;
    }
    Err(format!(
        "unterminated {quote_name}-quoted string at position {start}"
    ))
}

fn starts_template(characters: &[char], index: usize) -> bool {
    characters.get(index) == Some(&'$') && characters.get(index + 1) == Some(&'{')
}

fn find_character(characters: &[char], needle: char, start: usize) -> Option<usize> {
    characters[start..]
        .iter()
        .position(|character| *character == needle)
        .map(|offset| start + offset)
}

fn is_symbol(character: char) -> bool {
    matches!(character, '(' | ')' | '[' | ']' | '{' | '}' | ',')
}

fn is_python_whitespace(character: char) -> bool {
    character.is_whitespace() || matches!(character, '\u{1c}'..='\u{1f}')
}
