//! Why a SQL macro file or call is rejected, with the locations and help the error names.

use crate::sql_macros::models::SqlMacroLocation;

/// A rejected SQL macro file or call.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlMacroError {
    pub code: &'static str,
    pub message: String,
    /// The call first, then the macro file, when both are known.
    pub locations: Vec<SqlMacroLocation>,
    pub help: Option<String>,
}

impl SqlMacroError {
    pub(crate) fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            locations: Vec::new(),
            help: None,
        }
    }

    /// An error built outside this crate.
    pub fn new_public(code: &'static str, message: impl Into<String>) -> Self {
        Self::new(code, message)
    }

    /// The error with `help` attached, for errors built outside this crate.
    pub fn with_help(self, help: impl Into<String>) -> Self {
        self.helped(help)
    }

    /// The error with `help` attached.
    pub(crate) fn helped(mut self, help: impl Into<String>) -> Self {
        self.help = Some(help.into());
        self
    }

    /// The error located at `location` too.
    pub fn at(mut self, location: SqlMacroLocation) -> Self {
        if !self.locations.contains(&location) {
            self.locations.push(location);
        }
        self
    }

    /// The error located at the call first, before the locations it already names.
    pub fn at_call(mut self, location: SqlMacroLocation) -> Self {
        if !self.locations.contains(&location) {
            self.locations.insert(0, location);
        }
        self
    }

    /// The message with the model it was raised for and every location below it.
    pub fn located_message(&self, model: Option<&str>) -> String {
        let mut text: String = self.message.clone();
        if let Some(model) = model {
            text.push_str(&format!("\n  model: {model}"));
        }
        for location in &self.locations {
            text.push_str(&format!(
                "\n  --> {}:{}:{}",
                location.path, location.line, location.column
            ));
        }
        text
    }
}

/// A failure while expanding: a SQL macro error, or the host's own error, passed through.
#[derive(Debug)]
pub enum ExpansionFailure<E> {
    Macro(SqlMacroError),
    Host(E),
}

impl<E> From<SqlMacroError> for ExpansionFailure<E> {
    fn from(error: SqlMacroError) -> Self {
        Self::Macro(error)
    }
}

/// Why a scan stopped early.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum LexError {
    UnclosedQuote(usize),
    UnclosedComment(usize),
    /// A `"` that ends a `"..."` header string inside its text, at this offset.
    QuoteInside(usize),
    /// A `'` that ends a `'...'` header description inside its text, at this offset.
    SingleQuoteInside(usize),
    /// A `"""` that ends a `"""..."""` header string inside its text, at this offset.
    TripleQuoteInside(usize),
    /// A `"""` header string that opens at this offset and never closes.
    UnclosedTripleQuote(usize),
}
