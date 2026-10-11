//! Why a project configuration file is rejected.

use crate::project::constants::PYTHON_INT_MAX_STR_DIGITS;
use crate::project::models::ConfigFile;

/// One piece of a rejection message: fixed text or the path of a configuration file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MessagePiece {
    Text(String),
    File(ConfigFile),
}

/// The Python exception a rejection raises.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum FailureClass {
    /// `ProjectConfigError`.
    #[default]
    ProjectConfig,
    /// The `ValueError` `int()` raises for more digits than CPython converts.
    IntegerDigits,
}

/// A rejection message, its optional help, and the exception it raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConfigFailure {
    pub message: Vec<MessagePiece>,
    pub help: Option<String>,
    pub class: FailureClass,
}

impl ConfigFailure {
    /// A message without a file path.
    pub fn plain(text: impl Into<String>) -> Self {
        Self {
            message: vec![MessagePiece::Text(text.into())],
            help: None,
            class: FailureClass::ProjectConfig,
        }
    }

    /// A message that starts with the path of `file`.
    pub fn at(file: ConfigFile, text: impl AsRef<str>) -> Self {
        Self {
            message: vec![
                MessagePiece::File(file),
                MessagePiece::Text(format!(" {}", text.as_ref())),
            ],
            help: None,
            class: FailureClass::ProjectConfig,
        }
    }

    /// The `ValueError` of `int()` for a decimal string of `digits` digits.
    pub fn integer_digits(digits: usize) -> Self {
        Self {
            class: FailureClass::IntegerDigits,
            ..Self::plain(format!(
                "Exceeds the limit ({PYTHON_INT_MAX_STR_DIGITS} digits) for integer string \
                 conversion: value has {digits} digits; use sys.set_int_max_str_digits() to \
                 increase the limit"
            ))
        }
    }

    /// This failure with help text.
    pub fn with_help(self, help: impl Into<String>) -> Self {
        Self {
            help: Some(help.into()),
            ..self
        }
    }

    /// The message with each file path rendered by `path`.
    pub fn render(&self, path: impl Fn(ConfigFile) -> String) -> String {
        self.message
            .iter()
            .map(|piece| match piece {
                MessagePiece::Text(text) => text.clone(),
                MessagePiece::File(file) => path(*file),
            })
            .collect()
    }
}

/// Why a configuration file could not be loaded.
#[derive(Debug)]
pub enum LoadFailure {
    /// The file is rejected with a `ProjectConfigError`.
    Config(ConfigFailure),
    /// The file could not be read.
    Io(ConfigFile, std::io::Error),
    /// The file is not UTF-8; Python's decoder raises for these bytes.
    Utf8(Vec<u8>),
}

impl LoadFailure {
    /// The `ProjectConfigError` this failure raises, if it is one.
    pub fn into_config_failure(self) -> Option<ConfigFailure> {
        match self {
            Self::Config(failure) => Some(failure),
            Self::Io(..) | Self::Utf8(_) => None,
        }
    }
}

impl From<ConfigFailure> for LoadFailure {
    fn from(failure: ConfigFailure) -> Self {
        Self::Config(failure)
    }
}
