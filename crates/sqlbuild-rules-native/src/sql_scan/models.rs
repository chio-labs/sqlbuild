//! Lexical scanning outcomes and dialect-dependent quoting policy.

/// The SQL construct a scan reached the end of input inside.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Unclosed {
    BlockComment,
    Quote,
    Parenthesis,
}

/// Dialect-dependent quoting rules; comments and doubled-quote escapes are fixed for every policy.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct QuotePolicy {
    /// Backtick-delimited identifiers are quoted text.
    pub(crate) backtick_identifiers: bool,
    /// A backslash escapes the next byte inside single-quoted strings.
    pub(crate) single_quote_backslash_escapes: bool,
    /// A backslash escapes the next byte inside double-quoted text.
    pub(crate) double_quote_backslash_escapes: bool,
    /// `$$` and `$tag$` delimit opaque string literals.
    pub(crate) dollar_quotes: bool,
}

impl QuotePolicy {
    /// Compiler policy, mirroring Python `sql_analysis`: backticks and dollar quotes are text.
    pub(crate) const COMPILER: Self = Self {
        backtick_identifiers: true,
        single_quote_backslash_escapes: false,
        double_quote_backslash_escapes: false,
        dollar_quotes: true,
    };

    /// SQL lint policy: backslashes escape, backticks per dialect, dollar quotes as in the compiler.
    pub(crate) const SQL_LINT: Self = Self {
        backtick_identifiers: false,
        single_quote_backslash_escapes: true,
        double_quote_backslash_escapes: true,
        dollar_quotes: true,
    };

    /// Return this policy with backtick-delimited identifiers enabled or disabled.
    pub(crate) const fn with_backtick_identifiers(self, backtick_identifiers: bool) -> Self {
        Self {
            backtick_identifiers,
            ..self
        }
    }

    /// Return whether `byte` opens quoted text under this policy.
    pub(crate) fn is_quote(self, byte: u8) -> bool {
        match byte {
            b'\'' | b'"' => true,
            b'`' => self.backtick_identifiers,
            _ => false,
        }
    }

    /// Return whether a backslash escapes the next byte inside text opened by `quote`.
    pub(crate) fn backslash_escapes(self, quote: u8) -> bool {
        match quote {
            b'\'' => self.single_quote_backslash_escapes,
            b'"' => self.double_quote_backslash_escapes,
            _ => false,
        }
    }
}
