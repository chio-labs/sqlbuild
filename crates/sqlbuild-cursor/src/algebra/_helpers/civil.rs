//! Proleptic Gregorian dates and microsecond wall times within `datetime`'s year range.

use crate::algebra::_helpers::failures::overflow;
use crate::algebra::constants::{
    C_INT_OVERFLOW, CENTURY_YEARS, DATE_OUT_OF_RANGE, DAY_OUT_OF_RANGE, DAYS_IN_MONTH, FEBRUARY,
    FIRST_NEXT_YEAR_INDEX, LEAP_CYCLE_YEARS, LEAP_YEARS, MARCH, MAX_C_INT, MAX_TIMEDELTA_DAYS,
    MAX_YEAR, MICROS_PER_DAY, MICROS_PER_SECOND, MIN_C_INT, MIN_YEAR, SECONDS_PER_HOUR,
    SECONDS_PER_MINUTE,
};
use crate::algebra::errors::CursorError;
use crate::algebra::models::{CivilDate, LocalDateTime};

/// Days from 0000-03-01 to 1970-01-01 in Howard Hinnant's civil-day algorithm.
const UNIX_EPOCH_SHIFT: i64 = 719_468;
/// `date(1970, 1, 1).toordinal()`.
const UNIX_EPOCH_ORDINAL: i64 = 719_163;
const DAYS_PER_ERA: i64 = 146_097;
const DAYS_PER_YEAR: i64 = 365;
const MARCH_BASED_MONTH_DAYS: i64 = 153;
const MARCH_OFFSET: i64 = 3;
const MONTHS_FROM_MARCH: i64 = 9;
const MARCH_DAY_ROUNDING: i64 = 2;
const MONTH_LENGTH_DIVISOR: i64 = 5;
const ERA_DAY_LIMIT: i64 = 146_096;
const FOUR_YEAR_DAYS: i64 = 1_460;
const CENTURY_DAYS: i64 = 36_524;

/// `calendar.isleap` for any year.
pub(crate) fn is_leap(year: i64) -> bool {
    year.rem_euclid(LEAP_YEARS) == 0
        && (year.rem_euclid(CENTURY_YEARS) != 0 || year.rem_euclid(LEAP_CYCLE_YEARS) == 0)
}

/// `calendar.monthrange(year, month)[1]` for a month in `1..=12`.
pub(crate) fn days_in_month(year: i64, month: u32) -> u32 {
    let base: u32 = DAYS_IN_MONTH[(month - 1) as usize];
    base + u32::from(month == FEBRUARY && is_leap(year))
}

/// `date.replace` validation: the year first, then the day of the month.
pub(crate) fn checked_date(year: i64, month: u32, day: u32) -> Result<CivilDate, CursorError> {
    if !(MIN_YEAR..=MAX_YEAR).contains(&year) {
        return Err(CursorError::Value(format!("year {year} is out of range")));
    }
    if day < 1 || day > days_in_month(year, month) {
        return Err(CursorError::Value(DAY_OUT_OF_RANGE.to_owned()));
    }
    Ok(CivilDate { year, month, day })
}

/// `date.toordinal()`.
pub(crate) fn ordinal(date: CivilDate) -> i64 {
    let year: i64 = date.year - i64::from(date.month <= FEBRUARY);
    let era: i64 = year.div_euclid(LEAP_CYCLE_YEARS);
    let year_of_era: i64 = year - era * LEAP_CYCLE_YEARS;
    let month: i64 = i64::from(date.month);
    let shifted_month: i64 = if month >= i64::from(MARCH) {
        month - MARCH_OFFSET
    } else {
        month + MONTHS_FROM_MARCH
    };
    let day_of_year: i64 = (MARCH_BASED_MONTH_DAYS * shifted_month + MARCH_DAY_ROUNDING)
        / MONTH_LENGTH_DIVISOR
        + i64::from(date.day)
        - 1;
    let day_of_era: i64 = year_of_era * DAYS_PER_YEAR + year_of_era / LEAP_YEARS
        - year_of_era / CENTURY_YEARS
        + day_of_year;
    era * DAYS_PER_ERA + day_of_era - UNIX_EPOCH_SHIFT + UNIX_EPOCH_ORDINAL
}

/// `date.fromordinal(value)`, failing as date arithmetic does outside the year range.
pub(crate) fn from_ordinal(value: i128) -> Result<CivilDate, CursorError> {
    let maximum: i128 = i128::from(ordinal(CivilDate {
        year: MAX_YEAR,
        month: 12,
        day: 31,
    }));
    if !(1..=maximum).contains(&value) {
        return Err(overflow(DATE_OUT_OF_RANGE));
    }
    let days: i64 = i64::try_from(value).map_err(|_| overflow(DATE_OUT_OF_RANGE))?
        - UNIX_EPOCH_ORDINAL
        + UNIX_EPOCH_SHIFT;
    let era: i64 = days.div_euclid(DAYS_PER_ERA);
    let day_of_era: i64 = days - era * DAYS_PER_ERA;
    let year_of_era: i64 = (day_of_era - day_of_era / FOUR_YEAR_DAYS + day_of_era / CENTURY_DAYS
        - day_of_era / ERA_DAY_LIMIT)
        / DAYS_PER_YEAR;
    let day_of_year: i64 = day_of_era
        - (DAYS_PER_YEAR * year_of_era + year_of_era / LEAP_YEARS - year_of_era / CENTURY_YEARS);
    let shifted_month: i64 =
        (MONTH_LENGTH_DIVISOR * day_of_year + MARCH_DAY_ROUNDING) / MARCH_BASED_MONTH_DAYS;
    let day: i64 = day_of_year
        - (MARCH_BASED_MONTH_DAYS * shifted_month + MARCH_DAY_ROUNDING) / MONTH_LENGTH_DIVISOR
        + 1;
    let month: i64 = if shifted_month < FIRST_NEXT_YEAR_INDEX {
        shifted_month + MARCH_OFFSET
    } else {
        shifted_month - MONTHS_FROM_MARCH
    };
    let year: i64 = year_of_era + era * LEAP_CYCLE_YEARS + i64::from(month < i64::from(MARCH));
    Ok(CivilDate {
        year,
        month: u32::try_from(month).map_err(|_| overflow(DATE_OUT_OF_RANGE))?,
        day: u32::try_from(day).map_err(|_| overflow(DATE_OUT_OF_RANGE))?,
    })
}

/// Midnight at the start of `date`.
pub(crate) fn midnight(date: CivilDate) -> LocalDateTime {
    LocalDateTime {
        date,
        hour: 0,
        minute: 0,
        second: 0,
        microsecond: 0,
    }
}

fn micros_of_day(local: &LocalDateTime) -> i128 {
    (i128::from(local.hour) * SECONDS_PER_HOUR
        + i128::from(local.minute) * SECONDS_PER_MINUTE
        + i128::from(local.second))
        * MICROS_PER_SECOND
        + i128::from(local.microsecond)
}

/// `date + timedelta(days=days)` for an already valid day count.
pub(crate) fn add_days(date: CivilDate, days: i128) -> Result<CivilDate, CursorError> {
    from_ordinal(i128::from(ordinal(date)) + days)
}

/// `datetime + timedelta(microseconds=delta)` for an already valid delta.
pub(crate) fn add_micros(local: &LocalDateTime, delta: i128) -> Result<LocalDateTime, CursorError> {
    let total: i128 = micros_of_day(local) + delta;
    let date: CivilDate = add_days(local.date, total.div_euclid(MICROS_PER_DAY))?;
    let remainder: i128 = total.rem_euclid(MICROS_PER_DAY);
    let seconds: i128 = remainder / MICROS_PER_SECOND;
    Ok(LocalDateTime {
        date,
        hour: (seconds / SECONDS_PER_HOUR) as u32,
        minute: (seconds % SECONDS_PER_HOUR / SECONDS_PER_MINUTE) as u32,
        second: (seconds % SECONDS_PER_MINUTE) as u32,
        microsecond: (remainder % MICROS_PER_SECOND) as u32,
    })
}

/// The microseconds of a `timedelta` built from `total`, failing as its constructor does.
pub(crate) fn timedelta_micros(total: i128) -> Result<i128, CursorError> {
    let days: i128 = total.div_euclid(MICROS_PER_DAY);
    if !(MIN_C_INT..=MAX_C_INT).contains(&days) {
        return Err(overflow(C_INT_OVERFLOW));
    }
    if days.abs() > MAX_TIMEDELTA_DAYS {
        return Err(CursorError::Overflow(format!(
            "days={days}; must have magnitude <= {MAX_TIMEDELTA_DAYS}"
        )));
    }
    Ok(total)
}

/// The whole days of a valid `timedelta` of `total` microseconds.
pub(crate) fn timedelta_days(total: i128) -> i128 {
    total.div_euclid(MICROS_PER_DAY)
}
