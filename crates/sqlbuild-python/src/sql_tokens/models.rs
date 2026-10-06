//! Canonical token values shared by the formatter invariant and change fingerprints.

/// One authored token with layout removed: keywords and built-in function names upper-cased.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct CanonicalToken {
    pub(crate) text: String,
}
