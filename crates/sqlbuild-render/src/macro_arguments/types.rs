//! What argument parsing asks of the host Python for Unicode text it does not decide itself.

/// Unicode lookups the host Python answers, so names match CPython's own tables.
pub trait ArgumentHost {
    /// `unicodedata.lookup(name)`, several characters for a named sequence, or `None`.
    fn character_named(&self, name: &str) -> Option<String>;
    /// The NFKC form of a non-ASCII identifier, or `None` when Python rejects it as one.
    fn identifier(&self, text: &str) -> Option<String>;
}
