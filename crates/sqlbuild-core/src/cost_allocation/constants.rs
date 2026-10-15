//! Python `decimal` context limits, Snowflake credit rates and allocation messages.

/// `decimal.getcontext().prec` of the default context.
pub(crate) const DECIMAL_PRECISION: usize = 28;
pub(crate) const SECONDS_PER_HOUR: u64 = 3_600;
pub(crate) const MICROS_PER_SECOND: f64 = 1_000_000.0;
pub(crate) const STANDARD_WAREHOUSE_TYPE: &str = "STANDARD";
pub(crate) const UNKNOWN_RESOURCE: &str = "unknown";
pub(crate) const RESULT_LIMIT_LIMITATION: &str =
    "Snowflake query-history result limit was reached.";
/// Credits per hour by uppercased Snowflake warehouse size.
pub(crate) const CREDITS_PER_HOUR: [(&str, u64); 10] = [
    ("X-SMALL", 1),
    ("SMALL", 2),
    ("MEDIUM", 4),
    ("LARGE", 8),
    ("X-LARGE", 16),
    ("2X-LARGE", 32),
    ("3X-LARGE", 64),
    ("4X-LARGE", 128),
    ("5X-LARGE", 256),
    ("6X-LARGE", 512),
];
/// The default `RESULT_LIMIT` of one Snowflake query-history read.
pub const QUERY_HISTORY_RESULT_LIMIT: usize = 10_000;
pub(crate) const QUERY_HISTORY_FUNCTION: &str = "INFORMATION_SCHEMA.QUERY_HISTORY";
pub(crate) const NULL_QUERY_TEXT: &str = "NULL AS QUERY_TEXT";
/// The rounding digit at which `ROUND_HALF_EVEN` looks past the first dropped digit.
pub(crate) const HALF_DIGIT: u8 = 5;
/// `str(Decimal)` switches to exponent form at or below this many left digits.
#[cfg(test)]
pub(crate) const SMALLEST_PLAIN_LEFT_DIGITS: i64 = -6;
/// The largest decimal digit, which carries when rounded up.
pub(crate) const MAX_DIGIT: u8 = 9;
