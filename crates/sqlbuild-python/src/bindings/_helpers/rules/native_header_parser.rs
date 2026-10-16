//! DSL header values parsed natively for header rules, compared as Python compares their objects.

use std::cell::RefCell;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods};
use sqlbuild_rules::dsl_headers::models::{ParseFailure, ParseOutcome};
use sqlbuild_rules::dsl_headers::types::HeaderParser;
use sqlbuild_sqltext::compiler::main::header_word_value::header_word_value;
use sqlbuild_sqltext::compiler::main::model_header_parsing::parse_batch;
use sqlbuild_sqltext::compiler::models::{AuthoredValue, HeaderWord};

use crate::bindings::_helpers::boundary::panics::value_error;
use crate::bindings::_helpers::records::ids::ErrorId;
use crate::bindings::_helpers::records::registry;
use crate::bindings::_helpers::sqltext::model_headers::header_failure;
use crate::bindings::types::CompilerDetach;

/// The path header rules report header syntax errors at.
const SENTINEL_PATH: &str = "<lint>";
const DESCRIPTION_KEY: &str = "description";
const NEGATIVE_ZERO: &str = "-0";
const ZERO: &str = "0";

/// Header values parsed natively; a rejected parse keeps its message for raising.
pub(crate) struct NativeHeaderParser<'py> {
    py: Python<'py>,
    rejected: RefCell<Option<ParseFailure>>,
}

impl<'py> NativeHeaderParser<'py> {
    pub(crate) fn new(py: Python<'py>) -> Self {
        Self {
            py,
            rejected: RefCell::new(None),
        }
    }

    /// The `ModelSqlParseError` of the last rejected parse.
    pub(crate) fn rejected_error(&self) -> PyErr {
        let Some(failure) = self.rejected.take() else {
            return PyValueError::new_err("no header parse was rejected");
        };
        let raised: PyResult<PyErr> = (|| {
            let keywords: Bound<'py, PyDict> = PyDict::new(self.py);
            keywords.set_item("help", failure.help)?;
            let error: Bound<'py, PyAny> = registry::error(self.py, ErrorId::ModelSqlParse)?
                .call((failure.message,), Some(&keywords))?;
            Ok(PyErr::from_value(error))
        })();
        raised.unwrap_or_else(|error| error)
    }
}

impl HeaderParser for NativeHeaderParser<'_> {
    type Values = AuthoredValue;
    type Error = PyErr;

    fn parse(&self, kind: &str, inner: &str) -> ParseOutcome<AuthoredValue, PyErr> {
        let headers: Vec<String> = vec![inner.to_owned()];
        let parsed = match self.py.compiler_detach(|| parse_batch(&headers)) {
            Ok(parsed) => parsed,
            Err(message) => {
                return ParseOutcome::Raised(
                    value_error(message.clone()),
                    ParseFailure {
                        message,
                        help: None,
                    },
                );
            }
        };
        let (value, _, error) = parsed.into_iter().next().unwrap_or((None, None, None));
        if let Some(value) = value {
            return ParseOutcome::Parsed(value);
        }
        let error: String = error.unwrap_or_else(|| "None".to_owned());
        let (detail, help, _) = header_failure(&error, inner, None);
        let failure: ParseFailure = ParseFailure {
            message: format!(
                "{kind}(...) in '{SENTINEL_PATH}' contains invalid SQLBuild header syntax: {detail}"
            ),
            help,
        };
        self.rejected.replace(Some(ParseFailure {
            message: failure.message.clone(),
            help: failure.help.clone(),
        }));
        ParseOutcome::Rejected(failure)
    }

    fn description(&self, values: &AuthoredValue) -> PyResult<Option<String>> {
        Ok(match map_value(values, DESCRIPTION_KEY) {
            Some(AuthoredValue::String(text)) => Some(text.clone()),
            Some(AuthoredValue::BareWord(word)) if header_word_value(word) == HeaderWord::Text => {
                Some(word.clone())
            }
            _ => None,
        })
    }

    fn same(&self, left: &AuthoredValue, right: &AuthoredValue) -> PyResult<bool> {
        Ok(python_equal(left, right))
    }
}

/// The value a header map projects for `key`: its last entry, as a Python dict keeps it.
pub(crate) fn map_value<'a>(values: &'a AuthoredValue, key: &str) -> Option<&'a AuthoredValue> {
    match values {
        AuthoredValue::Map(entries) => entries
            .iter()
            .rev()
            .find(|(name, _)| name == key)
            .map(|(_, value)| value),
        _ => None,
    }
}

/// A header map's keys once each, as the projected Python dict holds them.
pub(crate) fn map_keys(values: &AuthoredValue) -> Vec<&str> {
    let mut keys: Vec<&str> = Vec::new();
    if let AuthoredValue::Map(entries) = values {
        for (name, _) in entries {
            if !keys.contains(&name.as_str()) {
                keys.push(name);
            }
        }
    }
    keys
}

/// A scalar as its projected Python object compares.
#[derive(Debug, PartialEq)]
enum Scalar<'a> {
    None,
    Integer(i128),
    BigInteger(String),
    Float(f64),
    Text(&'a str),
}

fn scalar(value: &AuthoredValue) -> Option<Scalar<'_>> {
    Some(match value {
        AuthoredValue::Null => Scalar::None,
        AuthoredValue::Boolean(flag) => Scalar::Integer(i128::from(*flag)),
        AuthoredValue::String(text) => Scalar::Text(text),
        AuthoredValue::BareWord(word) => match header_word_value(word) {
            HeaderWord::Bool(flag) => Scalar::Integer(i128::from(flag)),
            HeaderWord::Null => Scalar::None,
            HeaderWord::Integer(digits) => match digits.parse::<i128>() {
                Ok(number) => Scalar::Integer(number),
                Err(_) => Scalar::BigInteger(digits),
            },
            HeaderWord::Float(number) => Scalar::Float(number),
            HeaderWord::Text => Scalar::Text(word),
        },
        _ => return None,
    })
}

fn scalars_equal(left: &Scalar<'_>, right: &Scalar<'_>) -> bool {
    match (left, right) {
        (Scalar::Integer(integer), Scalar::Float(float))
        | (Scalar::Float(float), Scalar::Integer(integer)) => {
            integral_float_text(*float).is_some_and(|text| text == integer.to_string())
        }
        (Scalar::BigInteger(digits), Scalar::Float(float))
        | (Scalar::Float(float), Scalar::BigInteger(digits)) => {
            integral_float_text(*float).is_some_and(|text| text == digits.trim_start_matches('+'))
        }
        (Scalar::Float(left), Scalar::Float(right)) => left == right,
        (left, right) => left == right,
    }
}

/// The exact decimal digits of an integral finite float, as Python compares it with an int.
fn integral_float_text(float: f64) -> Option<String> {
    if !float.is_finite() || float.trunc() != float {
        return None;
    }
    let text: String = format!("{float:.0}");
    Some(if text == NEGATIVE_ZERO {
        ZERO.to_owned()
    } else {
        text
    })
}

/// Whether two parsed header values project to equal Python objects.
pub(crate) fn python_equal(left: &AuthoredValue, right: &AuthoredValue) -> bool {
    if let (Some(left), Some(right)) = (scalar(left), scalar(right)) {
        return scalars_equal(&left, &right);
    }
    match (left, right) {
        (AuthoredValue::List(left), AuthoredValue::List(right))
        | (AuthoredValue::Tuple(left), AuthoredValue::Tuple(right))
        | (AuthoredValue::Set(left), AuthoredValue::Set(right)) => sequences_equal(left, right),
        (AuthoredValue::Map(_), AuthoredValue::Map(_)) => maps_equal(left, right),
        (AuthoredValue::TypedConstant(left), AuthoredValue::TypedConstant(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|(left, right)| left.0 == right.0 && python_equal(&left.1, &right.1))
        }
        (AuthoredValue::InlineSqlHook(left), AuthoredValue::InlineSqlHook(right)) => left == right,
        (
            AuthoredValue::NamedSqlHook(left_name, left_kwargs),
            AuthoredValue::NamedSqlHook(right_name, right_kwargs),
        )
        | (
            AuthoredValue::PythonHook(left_name, left_kwargs),
            AuthoredValue::PythonHook(right_name, right_kwargs),
        ) => {
            left_name == right_name
                && maps_equal(
                    &AuthoredValue::Map(left_kwargs.clone()),
                    &AuthoredValue::Map(right_kwargs.clone()),
                )
        }
        _ => false,
    }
}

fn sequences_equal(left: &[AuthoredValue], right: &[AuthoredValue]) -> bool {
    left.len() == right.len()
        && left
            .iter()
            .zip(right)
            .all(|(left, right)| python_equal(left, right))
}

fn maps_equal(left: &AuthoredValue, right: &AuthoredValue) -> bool {
    let (left_keys, right_keys) = (map_keys(left), map_keys(right));
    left_keys.len() == right_keys.len()
        && left_keys
            .iter()
            .all(|key| match (map_value(left, key), map_value(right, key)) {
                (Some(left), Some(right)) => python_equal(left, right),
                _ => false,
            })
}
