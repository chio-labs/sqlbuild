//! Python's `@[A-Za-z_][A-Za-z0-9_]*\s*\(` search over one string.

use crate::config_presence::models::Presence;

/// Search `text` for a macro call opening, deferring where Python's `\s` decides.
pub(crate) fn macro_call(text: &str) -> Presence {
    let bytes = text.as_bytes();
    let mut deferred = false;
    for (at, _) in text.match_indices('@') {
        let mut index = at + 1;
        if !bytes
            .get(index)
            .is_some_and(|byte| byte.is_ascii_alphabetic() || *byte == b'_')
        {
            continue;
        }
        while bytes
            .get(index)
            .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
        {
            index += 1;
        }
        while bytes.get(index).copied().is_some_and(is_python_ascii_space) {
            index += 1;
        }
        match bytes.get(index) {
            Some(b'(') => return Presence::Present,
            Some(byte) if !byte.is_ascii() => deferred = true,
            _ => {}
        }
    }
    if deferred {
        Presence::Deferred
    } else {
        Presence::Absent
    }
}

/// ASCII characters Python's `\s` matches in a `str` pattern.
fn is_python_ascii_space(byte: u8) -> bool {
    matches!(byte, b'\t'..=b'\r' | 0x1c..=0x1f | b' ')
}
