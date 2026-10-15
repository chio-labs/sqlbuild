//! Text representations shared by command-output capture.

/// Text as Python's `str.encode("utf-8", "surrogatepass")` bytes, so lone surrogates survive.
pub type PassText = Vec<u8>;
