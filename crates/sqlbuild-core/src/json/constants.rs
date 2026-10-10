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
/// orjson refuses a dict, or a non-empty list, nested this many containers deep.
pub(crate) const ORJSON_MAX_CONTAINER_DEPTH: usize = 254;
/// CPython's default recursion limit, which bounds how deep `json.dumps` can nest.
pub(crate) const STDLIB_MAX_CONTAINER_DEPTH: usize = 1_000;
