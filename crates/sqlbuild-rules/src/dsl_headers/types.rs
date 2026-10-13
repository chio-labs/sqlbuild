//! The parser the header rules read header values with.

use crate::dsl_headers::models::ParseOutcome;

/// Parses the inner text of a header into values the rules read.
pub trait HeaderParser {
    type Values;
    type Error;

    /// Parse the text between a header's parentheses as a `kind` header.
    fn parse(&self, kind: &str, inner: &str) -> ParseOutcome<Self::Values, Self::Error>;

    /// The `description` value when it is a string.
    fn description(&self, values: &Self::Values) -> Result<Option<String>, Self::Error>;

    /// Whether two parses hold equal values.
    fn same(&self, left: &Self::Values, right: &Self::Values) -> Result<bool, Self::Error>;
}
