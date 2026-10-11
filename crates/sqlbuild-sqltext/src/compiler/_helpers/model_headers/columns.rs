//! Locate the `columns (...)` body of a MODEL header and each column entry in it.

use crate::compiler::_helpers::model_headers::tokenization::{
    HeaderToken, SYMBOL_TOKEN, WORD_TOKEN,
};
use crate::compiler::models::{HeaderColumnSpan, HeaderColumns};
use sqlbuild_core::constants::{CLOSE_PAREN, OPEN_PAREN};

const COLUMNS_KEY: &str = "columns";

fn is_symbol(token: &HeaderToken, symbol: &str) -> bool {
    token.0 == SYMBOL_TOKEN && token.1 == symbol
}

pub(crate) fn columns_open(tokens: &[HeaderToken]) -> Option<usize> {
    let mut depth: i64 = 0;
    for (index, token) in tokens.iter().enumerate() {
        let next_opens = tokens
            .get(index + 1)
            .is_some_and(|next| next.1 == OPEN_PAREN);
        if token.0 == WORD_TOKEN && token.1 == COLUMNS_KEY && depth == 0 && next_opens {
            return Some(index + 1);
        }
        if is_symbol(token, OPEN_PAREN) {
            depth += 1;
        } else if is_symbol(token, CLOSE_PAREN) {
            depth -= 1;
        }
    }
    None
}

/// The index of the token closing metadata opened at `open`, matched by value as Python does.
fn metadata_close(tokens: &[HeaderToken], open: usize) -> Option<usize> {
    let mut depth: i64 = 1;
    for (index, candidate) in tokens.iter().enumerate().skip(open + 1) {
        if candidate.1 == OPEN_PAREN {
            depth += 1;
        } else if candidate.1 == CLOSE_PAREN {
            depth -= 1;
            if depth == 0 {
                return Some(index);
            }
        }
    }
    None
}

fn record_entry(
    entries: Vec<(String, HeaderColumnSpan)>,
    name: &str,
    span: HeaderColumnSpan,
) -> Vec<(String, HeaderColumnSpan)> {
    let mut updated = entries;
    match updated.iter_mut().find(|(existing, _)| existing == name) {
        Some(entry) => entry.1 = span,
        None => updated.push((name.to_owned(), span)),
    }
    updated
}

/// Scan the tokens of a header starting at code point `header_start` from its columns opener.
pub(crate) fn scan_columns(
    tokens: &[HeaderToken],
    open: usize,
    header_start: usize,
) -> Result<Option<HeaderColumns>, String> {
    let mut entries: Vec<(String, HeaderColumnSpan)> = Vec::new();
    let mut depth: i64 = 1;
    let mut index = open + 1;
    while index < tokens.len() {
        let token = &tokens[index];
        if is_symbol(token, OPEN_PAREN) {
            depth += 1;
        } else if is_symbol(token, CLOSE_PAREN) {
            depth -= 1;
            if depth == 0 {
                return Ok(Some(HeaderColumns {
                    body_start: header_start + tokens[open].2 + 1,
                    body_end: header_start + token.2,
                    entries,
                }));
            }
        } else if token.0 == WORD_TOKEN && depth == 1 {
            let metadata_open = tokens
                .get(index + 1)
                .ok_or_else(|| "tuple index out of range".to_owned())?;
            if metadata_open.1 == OPEN_PAREN
                && let Some(close) = metadata_close(tokens, index + 1)
            {
                let span = HeaderColumnSpan {
                    entry_start: header_start + token.2,
                    entry_end: header_start + tokens[close].2 + 1,
                    metadata_start: header_start + metadata_open.2 + 1,
                    metadata_end: header_start + tokens[close].2,
                };
                entries = record_entry(entries, &token.1, span);
                index = close;
            }
        }
        index += 1;
    }
    Ok(None)
}
