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
