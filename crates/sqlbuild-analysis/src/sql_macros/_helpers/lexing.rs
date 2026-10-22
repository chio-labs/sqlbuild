//! A small comment- and quote-aware SQL token scan over byte offsets.

use crate::sql_macros::errors::LexError;

/// What one token is.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum TokenKind {
    /// An unquoted identifier or keyword.
    Word,
    /// A `"double"` or `` `backtick` `` quoted identifier, or a double-quoted header string.
    Quoted,
    /// A `'single'` or `$tag$dollar$tag$` quoted string.
    Text,
    Number,
    /// One of `( ) [ ] { } , . ;`.
    Punct,
    /// Any other operator character run, such as `:=`, `<>` or `@`.
    Operator,
}

/// One token and its byte span.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Token {
    pub(crate) kind: TokenKind,
    pub(crate) start: usize,
    pub(crate) end: usize,
}

impl Token {
    pub(crate) fn text<'a>(&self, sql: &'a str) -> &'a str {
        &sql[self.start..self.end]
    }

    /// Whether the token is the word `keyword`, ignoring case.
    pub(crate) fn is_word(&self, sql: &str, keyword: &str) -> bool {
        self.kind == TokenKind::Word && self.text(sql).eq_ignore_ascii_case(keyword)
    }

    /// Whether the token is the punctuation or operator `symbol`.
    pub(crate) fn is(&self, sql: &str, symbol: &str) -> bool {
        matches!(self.kind, TokenKind::Punct | TokenKind::Operator) && self.text(sql) == symbol
    }
}

const PUNCTUATION: &[u8] = b"()[]{},.;";

/// Every token of `sql`, skipping whitespace and comments.
///
/// Doubled quotes escape a quote; text that leaves a quote unclosed that way is read again
/// with backslash escapes, as BigQuery and Databricks strings use them.
pub(crate) fn tokens(sql: &str) -> Result<Vec<Token>, LexError> {
    match scanned_tokens(sql, false) {
        Err(LexError::UnclosedQuote(start)) => {
            scanned_tokens(sql, true).map_err(|_| LexError::UnclosedQuote(start))
        }
        scanned => scanned,
    }
}

fn scanned_tokens(sql: &str, backslash_escapes: bool) -> Result<Vec<Token>, LexError> {
    let bytes: &[u8] = sql.as_bytes();
    let mut found: Vec<Token> = Vec::new();
    let mut index: usize = 0;
    while index < bytes.len() {
        let byte: u8 = bytes[index];
        if byte.is_ascii_whitespace() {
            index += 1;
            continue;
        }
        if byte == b'-' && bytes.get(index + 1) == Some(&b'-') {
            index = bytes[index..]
                .iter()
                .position(|byte| *byte == b'\n')
                .map_or(bytes.len(), |offset| index + offset + 1);
            continue;
        }
        if byte == b'/' && bytes.get(index + 1) == Some(&b'*') {
            index = bytes[index + 2..]
                .windows(2)
                .position(|pair| pair == b"*/")
                .map(|offset| index + 2 + offset + 2)
                .ok_or(LexError::UnclosedComment(index))?;
            continue;
        }
        let start: usize = index;
        let kind: TokenKind = match byte {
            b'\'' => {
                index = quote_end(bytes, index, backslash_escapes)
                    .ok_or(LexError::UnclosedQuote(start))?;
                TokenKind::Text
            }
            b'"' | b'`' => {
                index = quote_end(bytes, index, backslash_escapes)
                    .ok_or(LexError::UnclosedQuote(start))?;
                TokenKind::Quoted
            }
            b'$' if dollar_end(bytes, index).is_some() => {
                index = dollar_end(bytes, index).ok_or(LexError::UnclosedQuote(start))?;
                TokenKind::Text
            }
            _ if byte.is_ascii_digit() => {
                index += 1;
                while index < bytes.len()
                    && (bytes[index].is_ascii_alphanumeric() || bytes[index] == b'.')
                {
                    index += 1;
                }
                TokenKind::Number
            }
            _ if is_word_start(sql, index) => {
                index = word_end(sql, index);
                TokenKind::Word
            }
            _ if PUNCTUATION.contains(&byte) => {
                index += 1;
                TokenKind::Punct
            }
            _ => {
                index += sql[index..].chars().next().map_or(1, char::len_utf8);
                while index < bytes.len()
                    && is_operator_byte(bytes[index])
                    && !(bytes[index] == b'-' && bytes.get(index + 1) == Some(&b'-'))
                    && !(bytes[index] == b'/' && bytes.get(index + 1) == Some(&b'*'))
                    && bytes[index - 1] != b'@'
                {
                    index += 1;
                }
                TokenKind::Operator
            }
        };
        found.push(Token {
            kind,
            start,
            end: index,
        });
    }
    Ok(found)
}

fn is_operator_byte(byte: u8) -> bool {
    matches!(
        byte,
        b'<' | b'>'
            | b'='
            | b'!'
            | b':'
            | b'|'
            | b'&'
            | b'+'
            | b'-'
            | b'*'
            | b'/'
            | b'%'
            | b'^'
            | b'~'
    )
}

fn is_word_start(sql: &str, index: usize) -> bool {
    sql[index..]
        .chars()
        .next()
        .is_some_and(|character| character == '_' || character.is_alphabetic())
}

/// The byte offset after the identifier starting at `index`.
pub(crate) fn word_end(sql: &str, index: usize) -> usize {
    let mut end: usize = index;
    for character in sql[index..].chars() {
        if character == '_' || character == '$' || character.is_alphanumeric() {
            end += character.len_utf8();
        } else {
            break;
        }
    }
    end
}

/// The byte offset after the quoted text starting at `start`; doubled quotes escape.
pub(crate) fn quoted_end(bytes: &[u8], start: usize) -> Option<usize> {
    let quote: u8 = bytes[start];
    let mut index: usize = start + 1;
    loop {
        index += bytes.get(index..)?.iter().position(|byte| *byte == quote)?;
        if bytes.get(index + 1) == Some(&quote) {
            index += 2;
            continue;
        }
        return Some(index + 1);
    }
}

/// The byte offset after the quoted text at `start`, where a backslash may escape the next byte.
fn quote_end(bytes: &[u8], start: usize, backslash_escapes: bool) -> Option<usize> {
    if !backslash_escapes {
        return quoted_end(bytes, start);
    }
    let quote: u8 = bytes[start];
    let mut index: usize = start + 1;
    while let Some(byte) = bytes.get(index) {
        if *byte == b'\\' {
            index += 2;
            continue;
        }
        if *byte == quote {
            if bytes.get(index + 1) == Some(&quote) {
                index += 2;
                continue;
            }
            return Some(index + 1);
        }
        index += 1;
    }
    None
}

/// The byte offset after a `$tag$...$tag$` string starting at `start`, if one starts there.
fn dollar_end(bytes: &[u8], start: usize) -> Option<usize> {
    if start
        .checked_sub(1)
        .is_some_and(|previous| bytes[previous].is_ascii_alphanumeric() || bytes[previous] == b'_')
    {
        return None;
    }
    let tag_end: usize = bytes[start + 1..]
        .iter()
        .position(|byte| !(byte.is_ascii_alphanumeric() || *byte == b'_'))
        .map_or(bytes.len(), |offset| start + 1 + offset);
    if bytes.get(tag_end) != Some(&b'$') || bytes.get(start + 1).is_some_and(u8::is_ascii_digit) {
        return None;
    }
    let delimiter: &[u8] = &bytes[start..=tag_end];
    bytes[tag_end + 1..]
        .windows(delimiter.len())
        .position(|window| window == delimiter)
        .map(|offset| tag_end + 1 + offset + delimiter.len())
}

/// The index of the token closing the bracket token at `open`, if it closes.
pub(crate) fn closing_token(sql: &str, tokens: &[Token], open: usize) -> Option<usize> {
    let mut depth: usize = 0;
    for (index, token) in tokens.iter().enumerate().skip(open) {
        if token.kind != TokenKind::Punct {
            continue;
        }
        match token.text(sql) {
            "(" | "[" | "{" => depth += 1,
            ")" | "]" | "}" => {
                depth = depth.checked_sub(1)?;
                if depth == 0 {
                    return Some(index);
                }
            }
            _ => {}
        }
    }
    None
}

/// The one-based line and column of byte `offset` in `text`, columns counting characters.
pub(crate) fn line_column(text: &str, offset: usize) -> (usize, usize) {
    let before: &str = &text[..offset.min(text.len())];
    let line: usize = before.matches('\n').count() + 1;
    let line_start: usize = before.rfind('\n').map_or(0, |newline| newline + 1);
    (line, before[line_start..].chars().count() + 1)
}
