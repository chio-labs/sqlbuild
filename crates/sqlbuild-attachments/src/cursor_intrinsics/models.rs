//! Outcome of the native cursor intrinsic check.

/// Whether SQL is free of cursor intrinsics, or the error rejecting it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum IntrinsicCheck {
    Free,
    Rejected(String),
}

/// The model whose query is checked: name, built-in incremental flag and string `cursor`.
#[derive(Clone, Copy, Debug)]
pub struct IntrinsicModel<'model> {
    pub name: &'model str,
    pub incremental: bool,
    pub cursor: Option<&'model str>,
}

/// Where one replaced intrinsic call was in the source and is in the output, in bytes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct IntrinsicSpan {
    pub source_start: usize,
    pub source_end: usize,
    pub output_start: usize,
    pub output_end: usize,
}
