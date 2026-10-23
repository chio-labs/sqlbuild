//! Whether an unprefixed `@name` is a macro call, the one rule every scanner applies.

/// Whether the `@name` ending at byte `name_end` of `text` opens a call, `(` right after it.
#[must_use]
pub fn opens_bare_call(text: &str, name_end: usize) -> bool {
    text.as_bytes().get(name_end) == Some(&b'(')
}
