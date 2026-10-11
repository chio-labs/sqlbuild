//! Authored values as normalization reads them.

/// An authored value: the Python objects `normalize_sql_value` accepts, by exact type.
#[derive(Clone, Debug, PartialEq)]
pub enum RawSqlValue {
    Null,
    Bool(bool),
    /// An `int` in the signed 64-bit range.
    Int(i64),
    /// Any other `int`, as `str(value)`.
    BigInt(String),
    Float(f64),
    /// A `Decimal`, as `str(value)`.
    Decimal(String),
    Str(String),
    List(Vec<RawSqlValue>),
    /// An `AuthoredSqlSet`.
    Set(Vec<RawSqlValue>),
    Object(Vec<(RawKey, RawSqlValue)>),
    /// An `AuthoredSqlValueCall`: the `constant(...)` arguments in authored order.
    Call(Vec<(String, RawSqlValue)>),
    /// Any other object, by `type(value).__name__`.
    Other(String),
}

/// An object key: a `str`, or any other object by its `repr`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RawKey {
    Str(String),
    Other(String),
}

/// `SqlValueLimits`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SqlValueLimits {
    pub max_depth: i64,
    pub max_elements: i64,
    pub max_size: i64,
}

impl Default for SqlValueLimits {
    fn default() -> Self {
        Self {
            max_depth: 32,
            max_elements: 10_000,
            max_size: 1_000_000,
        }
    }
}

/// A parsed finite or special `Decimal`: sign, coefficient digits and exponent.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct DecimalNumber {
    pub(crate) negative: bool,
    pub(crate) special: Option<DecimalSpecial>,
    /// Coefficient digits without leading zeros; `"0"` for zero.
    pub(crate) digits: String,
    pub(crate) exponent: i64,
}

/// `Infinity`, `NaN` or `sNaN` with its diagnostic payload digits.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum DecimalSpecial {
    Infinity,
    NaN(String),
    SignalingNaN(String),
}
