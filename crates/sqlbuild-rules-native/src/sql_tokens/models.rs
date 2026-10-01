//! Canonical token values shared by the formatter invariant and change fingerprints.

/// One authored token with layout removed: unquoted words upper-cased, all else exact.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct CanonicalToken {
    pub(crate) text: String,
}
