//! Python's `@[A-Za-z_][A-Za-z0-9_]*\s*\(` search over one string.

use sqlbuild_core::text::main::is_python_space::is_python_space;

/// Whether `text` holds a macro call opening; `\s` is Python's Unicode whitespace class.
pub(crate) fn macro_call(text: &str) -> bool {
    let bytes = text.as_bytes();
    text.match_indices('@').any(|(at, _)| {
        let mut index = at + 1;
        if !bytes
            .get(index)
            .is_some_and(|byte| byte.is_ascii_alphabetic() || *byte == b'_')
        {
            return false;
        }
        while bytes
            .get(index)
            .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
        {
            index += 1;
        }
        text[index..]
            .chars()
            .find(|character| !is_python_space(*character))
            == Some('(')
    })
}
