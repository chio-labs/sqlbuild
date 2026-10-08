//! Errors the native config stages report exactly as the Python stages raise them.

/// The Python exception class one error raises.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ErrorClass {
    /// `CompileInputError`.
    CompileInput,
    /// `ConfigValueTypeError` for a config key that must hold a string.
    ConfigValueType,
    /// `ResourceIdentityError` for an identity that is not canonical snake_case.
    ResourceIdentity,
    /// `DiscoveryConflictError` for equally specific path-default keys.
    DiscoveryConflict,
}

/// One error with the class, message, code and help the Python stage raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConfigError {
    pub class: ErrorClass,
    /// The message; empty for `ConfigValueTypeError`, which Python words from the value's type.
    pub message: String,
    /// The diagnostic code when it is not the class default.
    pub code: Option<&'static str>,
    pub help: Option<String>,
    /// The config key a `ConfigValueTypeError` names.
    pub key: Option<String>,
}

impl ConfigError {
    /// A `CompileInputError` with this message.
    pub fn compile(message: String) -> Self {
        Self {
            class: ErrorClass::CompileInput,
            message,
            code: None,
            help: None,
            key: None,
        }
    }

    /// The `ConfigValueTypeError` `get_config_str` raises for a non-string `key`.
    pub fn config_value_type(key: &str) -> Self {
        Self {
            class: ErrorClass::ConfigValueType,
            message: String::new(),
            code: None,
            help: None,
            key: Some(key.to_owned()),
        }
    }

    /// This error of another class.
    pub fn with_class(mut self, class: ErrorClass) -> Self {
        self.class = class;
        self
    }

    /// This error with help text.
    pub fn with_help(mut self, help: impl Into<String>) -> Self {
        self.help = Some(help.into());
        self
    }

    /// This error with a diagnostic code.
    pub fn with_code(mut self, code: &'static str) -> Self {
        self.code = Some(code);
        self
    }
}
