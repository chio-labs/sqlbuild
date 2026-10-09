//! Word a template error exactly as the Python template resolver does.

use crate::templates::errors::TemplateError;

/// Return the `CompileInputError` message for `error` in the context named `label`.
pub fn template_error_message(error: &TemplateError, label: &str) -> String {
    match error {
        TemplateError::UnknownVariable(name) => {
            format!("{label} references unknown variable '{name}'")
        }
        TemplateError::MissingEnvironment(name) => {
            format!("{label} references missing ENV variable '{name}'")
        }
        TemplateError::UnknownContext(name) => {
            format!("{label} references unknown CTX key '{name}'")
        }
        TemplateError::UnavailableContext(name) => {
            format!("{label} references CTX key '{name}' but no value is available")
        }
        TemplateError::ContextNotAllowed => format!("{label} does not allow CTX templates"),
        TemplateError::UnsupportedNamespace(namespace) => {
            format!("{label} references unsupported template namespace '{namespace}'")
        }
        TemplateError::ArgumentCount { function, expected } => {
            format!("{label} {function}(...) expects {expected}")
        }
        TemplateError::UnsupportedFunction(name) => {
            format!("{label} references unsupported template function '{name}'")
        }
        TemplateError::UnexpectedToken { token, position } => {
            format!(
                "template expression contains unexpected token '{token}' at position {position}"
            )
        }
        TemplateError::ExpectedSymbol { symbol, position } => {
            format!("template expression expected '{symbol}' at position {position}")
        }
        TemplateError::UnterminatedEscape { position } => {
            format!("template expression has unterminated escape at position {position}")
        }
        TemplateError::UnterminatedString { quote, position } => format!(
            "template expression has unterminated {quote}-quoted string at position {position}"
        ),
        TemplateError::Message(message) => message.clone(),
    }
}

/// Whether Python's `coalesce` treats this error message as a missing value and skips it.
pub fn is_missing_value_message(message: &str) -> bool {
    MISSING_VALUE_PARTS
        .iter()
        .any(|part| message.contains(part))
        || (message.contains(UNAVAILABLE_CONTEXT_PART) && message.contains(NO_VALUE_PART))
}

const MISSING_VALUE_PARTS: [&str; 3] = [
    "references missing ENV variable",
    "references unknown variable",
    "references unknown CTX key",
];
const UNAVAILABLE_CONTEXT_PART: &str = "references CTX key";
const NO_VALUE_PART: &str = "no value is available";
