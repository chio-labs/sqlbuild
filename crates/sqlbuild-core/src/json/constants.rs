//! Serializer constants.

pub(crate) const ORJSON_MIN_INTEGER: i128 = i64::MIN as i128;
pub(crate) const ORJSON_MAX_INTEGER: i128 = u64::MAX as i128;
pub(crate) const FIRST_PRINTABLE_ASCII: char = ' ';
pub(crate) const PYTHON_FIXED_EXPONENTS: std::ops::RangeInclusive<i32> = -4..=15;
pub(crate) const ORJSON_FIXED_EXPONENTS: std::ops::RangeInclusive<i32> = -5..=15;
pub(crate) const PYTHON_EXPONENT_DIGITS: usize = 2;
pub(crate) const ORJSON_EXPONENT_DIGITS: usize = 1;
/// CPython's default `sys.get_int_max_str_digits()`, beyond which `int.__repr__` raises.
pub(crate) const PYTHON_INT_MAX_STR_DIGITS: usize = 4_300;
/// Containers nested deeper than this are refused; orjson's own limit is 255 and json's is higher.
pub(crate) const MAX_NESTING_DEPTH: usize = 128;
