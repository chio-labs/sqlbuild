//! Python values on their way to `json.dumps`, keeping what Python's type checks see.

use sqlbuild_core::json::models::JsonInteger;

/// A Python value as `json.dumps` would encode it.
#[derive(Clone, Debug, PartialEq)]
pub enum PythonValue {
    Null,
    Bool(bool),
    Integer(JsonInteger),
    Float(f64),
    String(String),
    /// A `str` holding lone surrogates, as UTF-16 code units.
    Utf16(Vec<u16>),
    /// A `list` or `tuple`.
    Array(Vec<PythonValue>),
    /// A `dict`, in insertion order.
    Object(Vec<(PythonKey, PythonValue)>),
    /// A value `json.dumps` refuses, with the message of its `TypeError`.
    Unencodable(String),
}

/// A `dict` key: the text `json.dumps` writes, or its `TypeError` message, and whether it is a `str`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PythonKey {
    pub text: Result<String, String>,
    pub is_str: bool,
}
