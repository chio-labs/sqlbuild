//! The template errors the Python resolver raises.

/// One template error the Python resolver raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TemplateError {
    UnknownVariable(String),
    MissingEnvironment(String),
    UnknownContext(String),
    UnavailableContext(String),
    ContextNotAllowed,
    UnsupportedNamespace(String),
    /// A function called with the wrong number of arguments, and the count it expects.
    ArgumentCount {
        function: &'static str,
        expected: &'static str,
    },
    UnsupportedFunction(String),
    /// A token the parser does not expect, at its character position in the expression.
    UnexpectedToken {
        token: String,
        position: usize,
    },
    ExpectedSymbol {
        symbol: char,
        position: usize,
    },
    UnterminatedEscape {
        position: usize,
    },
    /// A string missing its closing quote, named `single` or `double`.
    UnterminatedString {
        quote: &'static str,
        position: usize,
    },
    /// An error the host worded, such as a value that cannot be interpolated as text.
    Message(String),
}
