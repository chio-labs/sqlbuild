//! Calendar limits of Python's `datetime` types and characters shared by the readers.

pub(crate) const MIN_YEAR: i64 = 1;
pub(crate) const MAX_YEAR: i64 = 9999;
pub(crate) const MONTHS_PER_YEAR: i64 = 12;
pub(crate) const FEBRUARY: i64 = 2;
pub(crate) const MAX_HOUR: i64 = 23;
pub(crate) const MAX_MINUTE: i64 = 59;
pub(crate) const MAX_SECOND: i64 = 59;
pub(crate) const MAX_MICROSECOND: i64 = 999_999;
pub(crate) const BYTE_ORDER_MARK: char = '\u{feff}';
