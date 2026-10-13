//! `shift_by_duration`: a date or timestamp moved by a calendar duration.

use crate::algebra::_helpers::civil::{
    add_days, add_micros, checked_date, days_in_month, timedelta_days, timedelta_micros,
};
use crate::algebra::constants::{
    MICROS_PER_SECOND, MONTHS_PER_YEAR, SECONDS_PER_DAY, SECONDS_PER_HOUR, SECONDS_PER_MINUTE,
};
use crate::algebra::errors::CursorError;
use crate::algebra::models::{CivilDate, DurationSpan, Moment};

/// `moment.replace(year, month, day)` `delta` months on, with the day clamped to the month.
fn shift_months(date: CivilDate, delta: i64) -> Result<CivilDate, CursorError> {
    let total: i64 = date.year * MONTHS_PER_YEAR + i64::from(date.month) - 1 + delta;
    let year: i64 = total.div_euclid(MONTHS_PER_YEAR);
    let month: u32 = (total.rem_euclid(MONTHS_PER_YEAR) + 1) as u32;
    checked_date(year, month, date.day.min(days_in_month(year, month)))
}

/// `Duration.add_to` for a positive `direction`, `Duration.subtract_from` for a negative one.
pub fn shift_by_duration(
    moment: Moment,
    span: &DurationSpan,
    direction: i64,
) -> Result<Moment, CursorError> {
    let months: i64 = span.months * direction;
    let shifted: Moment = match moment {
        _ if months == 0 => moment,
        Moment::Date(date) => Moment::Date(shift_months(date, months)?),
        Moment::Timestamp { mut local, fold } => {
            local.date = shift_months(local.date, months)?;
            Moment::Timestamp { local, fold }
        }
    };
    let fixed: i128 = timedelta_micros(
        (i128::from(span.days) * SECONDS_PER_DAY
            + i128::from(span.hours) * SECONDS_PER_HOUR
            + i128::from(span.minutes) * SECONDS_PER_MINUTE
            + i128::from(span.seconds))
            * MICROS_PER_SECOND,
    )?;
    let sign: i128 = i128::from(direction.signum());
    Ok(match shifted {
        Moment::Date(date) => Moment::Date(add_days(date, sign * timedelta_days(fixed))?),
        Moment::Timestamp { local, .. } => Moment::Timestamp {
            local: add_micros(&local, sign * fixed)?,
            fold: false,
        },
    })
}
