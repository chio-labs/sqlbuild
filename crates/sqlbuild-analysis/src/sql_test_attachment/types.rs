//! The text matching the SQL-test attachment checks are given by their host.

/// The text pattern matches SQL-test attachment checks need, with the host's own semantics.
pub trait SqlTestTextMatcher {
    type Error;

    /// Every `[A-Za-z_][\w$]*` identifier token of `sql`, casefolded, first occurrence first.
    fn identifier_tokens(&self, sql: &str) -> Result<Vec<String>, Self::Error>;

    /// Whether `sql` contains `word`, ignoring case, outside a longer `[\w$]` run.
    fn reads_word(&self, sql: &str, word: &str) -> Result<bool, Self::Error>;
}
