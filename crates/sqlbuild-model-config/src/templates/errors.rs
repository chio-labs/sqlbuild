//! The errors Python's template resolver raises.

/// The error Python's template resolver raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TemplateError {
    UnknownVariable(String),
    MissingEnvironmentVariable(String),
    UnknownContextKey(String),
    UnavailableContextKey(String),
    ContextNotAllowed,
    UnsupportedNamespace(String),
    /// `if`, `eq` or `ne` with the wrong number of arguments, and the number it expects.
    ArgumentCount(&'static str, usize),
    CoalesceWithoutArguments,
    UnsupportedFunction(String),
    /// A token's text and character position where the parser expected another.
    UnexpectedToken(String, usize),
    ExpectedSymbol(char, usize),
    UnterminatedEscape(usize),
    /// The quote's name, `single` or `double`, and the position it opens at.
    UnterminatedString(&'static str, usize),
}

impl TemplateError {
    /// Python's message for templates in `context_label`; parse errors do not name it.
    #[must_use]
    pub fn message(&self, context_label: &str) -> String {
        match self {
            Self::UnknownVariable(name) => {
                format!("{context_label} references unknown variable '{name}'")
            }
            Self::MissingEnvironmentVariable(name) => {
                format!("{context_label} references missing ENV variable '{name}'")
            }
            Self::UnknownContextKey(name) => {
                format!("{context_label} references unknown CTX key '{name}'")
            }
            Self::UnavailableContextKey(name) => {
                format!("{context_label} references CTX key '{name}' but no value is available")
            }
            Self::ContextNotAllowed => format!("{context_label} does not allow CTX templates"),
            Self::UnsupportedNamespace(namespace) => {
                format!("{context_label} references unsupported template namespace '{namespace}'")
            }
            Self::ArgumentCount(function, count) => {
                format!("{context_label} {function}(...) expects {count} arguments")
            }
            Self::CoalesceWithoutArguments => {
                format!("{context_label} coalesce(...) expects at least 1 argument")
            }
            Self::UnsupportedFunction(name) => {
                format!("{context_label} references unsupported template function '{name}'")
            }
            Self::UnexpectedToken(token, position) => format!(
                "template expression contains unexpected token '{token}' at position {position}"
            ),
            Self::ExpectedSymbol(symbol, position) => {
                format!("template expression expected '{symbol}' at position {position}")
            }
            Self::UnterminatedEscape(position) => {
                format!("template expression has unterminated escape at position {position}")
            }
            Self::UnterminatedString(quote, position) => format!(
                "template expression has unterminated {quote}-quoted string at position {position}"
            ),
        }
    }
}
