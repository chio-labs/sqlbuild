//! SQL code with comments blanked and literals emptied, under one escape and bracket reading.

/// How ambiguous lexemes are read.
#[derive(Clone, Copy)]
pub(crate) struct LexicalMode {
    /// A backslash escapes the next character inside single-quoted literals.
    pub(crate) backslash_escapes: bool,
    /// `[...]` delimits a quoted identifier rather than plain code.
    pub(crate) bracket_identifiers: bool,
}

/// The next lexeme start at or after `position`: `--`, `/*`, a quote, `$` or `[`.
fn lexeme_start(bytes: &[u8], position: usize) -> Option<usize> {
    (position..bytes.len()).find(|index| match bytes[*index] {
        b'\'' | b'"' | b'`' | b'$' | b'[' => true,
        b'-' => bytes.get(index + 1) == Some(&b'-'),
        b'/' => bytes.get(index + 1) == Some(&b'*'),
        _ => false,
    })
}

/// Python's `text.find(needle, position)` as a byte offset.
fn find(text: &str, needle: &str, position: usize) -> Option<usize> {
    text.get(position..)?
        .find(needle)
        .map(|offset| position + offset)
}

/// The closing quote of a single-quoted literal opened at `begin`.
fn literal_end(text: &str, begin: usize, backslash_escapes: bool) -> Option<usize> {
    let bytes: &[u8] = text.as_bytes();
    let mut position: usize = begin + 1;
    loop {
        let rest: &[u8] = bytes.get(position..)?;
        let offset: usize = rest
            .iter()
            .position(|byte| *byte == b'\'' || (backslash_escapes && *byte == b'\\'))?;
        let stop: usize = position + offset;
        if bytes[stop] == b'\\' {
            let escaped: char = text[stop + 1..].chars().next()?;
            position = stop + 1 + escaped.len_utf8();
            continue;
        }
        if bytes.get(stop + 1) == Some(&b'\'') {
            position = stop + 2;
            continue;
        }
        return Some(stop);
    }
}

/// The closing `quote` of quoted text opened at `begin`; doubled quotes escape except `]`.
fn quoted_end(text: &str, begin: usize, quote: u8) -> Option<usize> {
    let bytes: &[u8] = text.as_bytes();
    let mut position: usize = begin + 1;
    loop {
        let offset: usize = bytes
            .get(position..)?
            .iter()
            .position(|byte| *byte == quote)?;
        let end: usize = position + offset;
        if quote == b']' || bytes.get(end + 1) != Some(&quote) {
            return Some(end);
        }
        position = end + 2;
    }
}

/// The end of a `$tag$` opener at `begin`, or `None` when `$` starts no tag.
fn dollar_tag_end(bytes: &[u8], begin: usize) -> Option<usize> {
    let length: usize = bytes[begin + 1..]
        .iter()
        .take_while(|byte| byte.is_ascii_alphabetic() || **byte == b'_')
        .count();
    let close: usize = begin + 1 + length;
    (bytes.get(close) == Some(&b'$')).then_some(close + 1)
}

/// One lexeme's code replacement and the position after it; `None` when it never closes.
fn read_lexeme(text: &str, begin: usize, mode: LexicalMode) -> Option<(&str, usize)> {
    let bytes: &[u8] = text.as_bytes();
    match bytes[begin] {
        b'-' => Some((" ", find(text, "\n", begin).unwrap_or(text.len()))),
        b'/' => find(text, "*/", begin + 2).map(|end| (" ", end + 2)),
        b'\'' => literal_end(text, begin, mode.backslash_escapes).map(|end| ("''", end + 1)),
        b'$' => match dollar_tag_end(bytes, begin) {
            None => Some(("$", begin + 1)),
            Some(tag_end) => {
                let tag: &str = &text[begin..tag_end];
                find(text, tag, tag_end).map(|end| ("''", end + tag.len()))
            }
        },
        b'[' if !mode.bracket_identifiers => Some(("[", begin + 1)),
        quote => {
            let closing: u8 = if quote == b'[' { b']' } else { quote };
            quoted_end(text, begin, closing).map(|end| (&text[begin..=end], end + 1))
        }
    }
}

/// `sql` with comments as spaces and literals as `''`, or `None` when a lexeme never closes.
pub(crate) fn code_text(sql: &str, mode: LexicalMode) -> Option<String> {
    let bytes: &[u8] = sql.as_bytes();
    let mut code: String = String::with_capacity(sql.len());
    let mut position: usize = 0;
    while let Some(start) = lexeme_start(bytes, position) {
        code.push_str(&sql[position..start]);
        let (replacement, next) = read_lexeme(sql, start, mode)?;
        code.push_str(replacement);
        position = next;
    }
    code.push_str(&sql[position..]);
    Some(code)
}
