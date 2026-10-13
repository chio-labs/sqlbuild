//! Cursor values, grains, intervals and durations.

/// A proleptic Gregorian date; the year may leave `datetime`'s range only inside arithmetic.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct CivilDate {
    pub year: i64,
    pub month: u32,
    pub day: u32,
}

/// A naive wall-clock date and time with microsecond precision.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct LocalDateTime {
    pub date: CivilDate,
    pub hour: u32,
    pub minute: u32,
    pub second: u32,
    pub microsecond: u32,
}

/// How a timestamp's wall time relates to UTC.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ZoneOffset {
    /// A naive timestamp, compared as written.
    Naive,
    /// A fixed `datetime.timezone` offset in microseconds.
    Fixed(i64),
    /// Any other `tzinfo`, resolved through the caller's `ZoneRules` for this input timestamp.
    External(usize),
}

/// A timestamp cursor value.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Timestamp {
    pub local: LocalDateTime,
    pub fold: bool,
    pub offset: ZoneOffset,
    /// The caller's input timestamp whose type and `tzinfo` this value keeps.
    pub template: Option<usize>,
    /// The text the value was parsed from, rendered in place of `isoformat()`.
    pub source_text: Option<String>,
}

/// The typed payload of a cursor value.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ScalarValue {
    Timestamp(Timestamp),
    Date(CivilDate),
    Integer(i128),
}

/// A cursor value and, while it is unchanged, the caller's handle for the input it came from.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Scalar {
    pub value: ScalarValue,
    pub handle: Option<usize>,
}

/// A cursor grain, from finest to coarsest.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Grain {
    Second,
    Minute,
    Hour,
    Day,
    Month,
    Year,
}

/// A half-open cursor interval.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Interval {
    pub start: Scalar,
    pub end: Scalar,
    pub grain: Option<Grain>,
}

/// The sortable projection of a cursor value: an integer, or a naive UTC wall time.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SortKey {
    Integer(i128),
    Moment(LocalDateTime),
}

/// The value a calendar duration moves: a date, or a timestamp's wall time and fold.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Moment {
    Date(CivilDate),
    Timestamp { local: LocalDateTime, fold: bool },
}

/// A parsed duration's whole-month and fixed parts, as Python integers would hold them.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DurationSpan {
    pub months: i64,
    pub days: i64,
    pub hours: i64,
    pub minutes: i64,
    pub seconds: i64,
}

/// The ASCII digits of each unit a duration string names, years first.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DurationDigits {
    pub years: String,
    pub months: String,
    pub days: String,
    pub hours: String,
    pub minutes: String,
    pub seconds: String,
}

/// Which end of an ordering `max()` or `min()` keeps.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Extreme {
    Max,
    Min,
}
