//! Values a Python serializer refuses.

/// A value the chosen serializer refuses, named after the Python failure it reproduces.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum JsonEmitError {
    /// `json.dumps(..., allow_nan=False)` met `NaN` or an infinity and raised `ValueError`.
    NonFiniteFloat,
    /// orjson met an integer outside `[-2**63, 2**64 - 1]` and raised `JSONEncodeError`.
    IntegerOutOfRange,
    /// `json.dumps` met an integer with more digits than Python's string conversion limit.
    IntegerTooLong,
    /// orjson's recursion limit, or `json.dumps` beyond Python's default recursion limit.
    NestingTooDeep,
    /// A lone surrogate under an encoder that writes text unescaped; Python cannot encode it.
    LoneSurrogate,
}
