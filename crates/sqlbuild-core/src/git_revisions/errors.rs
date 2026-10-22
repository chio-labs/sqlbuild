//! A `--since` ref that cannot be resolved or read, with its code and remedy.

/// The message, error code and help of one failed git step.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GitRevisionError {
    pub message: String,
    pub code: &'static str,
    pub help: String,
}
