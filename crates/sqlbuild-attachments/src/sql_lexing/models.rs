//! What Python's compiler scan finds at one offset.

/// Code, the end of a comment or quoted text, or input that makes Python raise.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NonCode {
    Code,
    End(usize),
    Raises,
}
