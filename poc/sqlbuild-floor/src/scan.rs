//! SQL text scanning shared by the render floor: quotes, comments, parentheses, call sites.

/// End (exclusive) of quoted text or comment starting at `index`, or None if not one.
pub fn non_code_end(bytes: &[u8], index: usize) -> Option<usize> {
    match bytes[index] {
        b'\'' | b'"' | b'`' => {
            let quote = bytes[index];
            let mut cursor = index + 1;
            while cursor < bytes.len() {
                if bytes[cursor] == quote {
                    if quote != b'`' && bytes.get(cursor + 1) == Some(&quote) {
                        cursor += 2;
                        continue;
                    }
                    return Some(cursor + 1);
                }
                cursor += 1;
            }
            Some(bytes.len())
        }
        b'$' => {
            let mut cursor = index + 1;
            while cursor < bytes.len()
                && (bytes[cursor].is_ascii_alphanumeric() || bytes[cursor] == b'_')
            {
                cursor += 1;
            }
            if bytes.get(cursor) != Some(&b'$')
                || bytes[index + 1..cursor]
                    .first()
                    .is_some_and(u8::is_ascii_digit)
            {
                return None;
            }
            let tag = &bytes[index..=cursor];
            let body = cursor + 1;
            (body..=bytes.len().saturating_sub(tag.len()))
                .find(|start| &bytes[*start..*start + tag.len()] == tag)
                .map(|start| start + tag.len())
                .or(Some(bytes.len()))
        }
        b'-' if bytes.get(index + 1) == Some(&b'-') => Some(
            bytes[index..]
                .iter()
                .position(|b| *b == b'\n')
                .map_or(bytes.len(), |offset| index + offset),
        ),
        b'/' if bytes.get(index + 1) == Some(&b'*') => Some(
            bytes[index + 2..]
                .windows(2)
                .position(|w| w == b"*/")
                .map_or(bytes.len(), |offset| index + 2 + offset + 2),
        ),
        _ => None,
    }
}

pub fn is_ident_start(byte: u8) -> bool {
    byte.is_ascii_alphabetic() || byte == b'_'
}

pub fn is_ident_continue(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

/// Index of the parenthesis closing the one at `open`, skipping quotes and comments.
pub fn matching_paren(bytes: &[u8], open: usize) -> Option<usize> {
    let mut depth = 0usize;
    let mut index = open;
    while index < bytes.len() {
        if let Some(end) = non_code_end(bytes, index) {
            index = end;
            continue;
        }
        match bytes[index] {
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return Some(index);
                }
            }
            _ => {}
        }
        index += 1;
    }
    None
}

pub fn skip_ws(bytes: &[u8], mut index: usize) -> usize {
    while index < bytes.len() && bytes[index].is_ascii_whitespace() {
        index += 1;
    }
    index
}

/// Next `@name(` macro or declaration call start at or after `from` in code (not quoted text).
pub fn next_call(bytes: &[u8], from: usize) -> Option<(usize, String, usize)> {
    let mut index = from;
    while index < bytes.len() {
        if let Some(end) = non_code_end(bytes, index) {
            index = end.max(index + 1);
            continue;
        }
        if bytes[index] == b'@'
            && bytes.get(index + 1).copied().is_some_and(is_ident_start)
            && (index == 0 || bytes[index - 1] != b'@')
        {
            let mut end = index + 2;
            while end < bytes.len() && is_ident_continue(bytes[end]) {
                end += 1;
            }
            let open = skip_ws(bytes, end);
            if bytes.get(open) == Some(&b'(') {
                let name = String::from_utf8_lossy(&bytes[index + 1..end]).into_owned();
                return Some((index, name, open));
            }
        }
        index += 1;
    }
    None
}
