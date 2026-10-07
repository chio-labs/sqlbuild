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
    /// The value nests deeper than the native emitter writes; callers fall back to Python.
    NestingTooDeep,
}
