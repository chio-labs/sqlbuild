//! Calendar sizes and Python's `datetime` limits the cursor algebra reproduces.

pub(crate) const MONTHS_PER_YEAR: i64 = 12;
pub(crate) const MIN_YEAR: i64 = 1;
pub(crate) const MAX_YEAR: i64 = 9999;
pub(crate) const MICROS_PER_SECOND: i128 = 1_000_000;
pub(crate) const SECONDS_PER_MINUTE: i128 = 60;
pub(crate) const SECONDS_PER_HOUR: i128 = 3_600;
pub(crate) const SECONDS_PER_DAY: i128 = 86_400;
pub(crate) const MICROS_PER_DAY: i128 = SECONDS_PER_DAY * MICROS_PER_SECOND;
/// `timedelta.max.days`.
pub(crate) const MAX_TIMEDELTA_DAYS: i128 = 999_999_999;
/// The largest C `int` a `timedelta` day count passes through.
pub(crate) const MAX_C_INT: i128 = i32::MAX as i128;
pub(crate) const MIN_C_INT: i128 = i32::MIN as i128;
pub(crate) const FEBRUARY: u32 = 2;
pub(crate) const DAYS_IN_MONTH: [u32; 12] = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
pub(crate) const LEAP_CYCLE_YEARS: i64 = 400;
pub(crate) const CENTURY_YEARS: i64 = 100;
pub(crate) const LEAP_YEARS: i64 = 4;

pub const DATE_OUT_OF_RANGE: &str = "date value out of range";
pub const DAY_OUT_OF_RANGE: &str = "day is out of range for month";
pub const C_INT_OVERFLOW: &str = "Python int too large to convert to C int";
pub const INTEGER_CURSOR_OVERFLOW: &str = "integer cursor value out of range";
pub const NON_POSITIVE_STEP: &str = "cursor batch step must be positive";
pub const TEMPORAL_VALUES_NEED_GRAIN: &str = "temporal cursor values require a grain";
pub const TEMPORAL_PARTITIONS_NEED_GRAIN: &str = "temporal observed partitions require a grain";
pub const TEMPORAL_BOUNDS_NEED_GRAIN: &str = "temporal inclusive bounds require a grain";
pub const TEMPORAL_INTERVALS_NEED_GRAIN: &str = "temporal cursor intervals require a grain";
pub const MIXED_COMPARISON: &str = "cannot compare temporal and integer cursor values";
pub const START_NOT_BEFORE_END: &str = "cursor interval start must be less than end";
pub const START_NOT_ALIGNED: &str = "cursor interval start must be grain-aligned";
pub const END_NOT_ALIGNED: &str = "cursor interval end must be grain-aligned";
pub const INTEGER_KEY_TYPE: &str = "int";
pub const MOMENT_KEY_TYPE: &str = "datetime.datetime";
pub const NO_GRAIN_STEP: &str = "a timestamp cursor value needs a grain to advance";
pub(crate) const MARCH: u32 = 3;
/// The first month index from March on that falls in the next calendar year.
pub(crate) const FIRST_NEXT_YEAR_INDEX: i64 = 10;
pub(crate) const UTC_DESIGNATOR: char = 'Z';
pub(crate) const OFFSET_SEPARATOR: char = ':';
pub(crate) const COMPACT_OFFSET_LENGTH: usize = 5;
pub(crate) const SEPARATED_OFFSET_LENGTH: usize = 6;
pub(crate) const SEPARATOR_POSITION: usize = 3;
/// Unit suffixes in the order a duration string must name them.
pub(crate) const UNIT_SUFFIXES: [&str; 6] = ["y", "mo", "d", "h", "m", "s"];
pub(crate) const LINE_FEED: char = '\n';
