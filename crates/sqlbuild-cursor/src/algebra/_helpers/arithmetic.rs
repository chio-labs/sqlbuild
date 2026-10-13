//! Flooring and stepping one cursor value by its grain.

use crate::algebra::_helpers::civil::{
    add_days, add_micros, checked_date, timedelta_days, timedelta_micros,
};
use crate::algebra::_helpers::failures::{algebra, overflow};
use crate::algebra::constants::{
    INTEGER_CURSOR_OVERFLOW, MICROS_PER_DAY, MICROS_PER_SECOND, MONTHS_PER_YEAR, NO_GRAIN_STEP,
    SECONDS_PER_HOUR, SECONDS_PER_MINUTE, TEMPORAL_VALUES_NEED_GRAIN,
};
use crate::algebra::errors::CursorError;
use crate::algebra::models::{CivilDate, Grain, LocalDateTime, Scalar, ScalarValue, Timestamp};

/// The fixed length of one grain in microseconds; months and years vary.
pub(crate) fn fixed_step(grain: Grain) -> Option<i128> {
    match grain {
        Grain::Second => Some(MICROS_PER_SECOND),
        Grain::Minute => Some(SECONDS_PER_MINUTE * MICROS_PER_SECOND),
        Grain::Hour => Some(SECONDS_PER_HOUR * MICROS_PER_SECOND),
        Grain::Day => Some(MICROS_PER_DAY),
        Grain::Month | Grain::Year => None,
    }
}

/// A new value with no input handle.
pub(crate) fn fresh(value: ScalarValue) -> Scalar {
    Scalar {
        value,
        handle: None,
    }
}

/// A new timestamp in `source`'s zone; `datetime + timedelta` resets `fold`, `replace` keeps it.
pub(crate) fn retimed(source: &Timestamp, local: LocalDateTime, fold: bool) -> Scalar {
    fresh(ScalarValue::Timestamp(Timestamp {
        local,
        fold,
        offset: source.offset,
        template: source.template,
        source_text: None,
    }))
}

pub(crate) fn integer_sum(value: i128, delta: i128) -> Result<i128, CursorError> {
    value
        .checked_add(delta)
        .ok_or_else(|| overflow(INTEGER_CURSOR_OVERFLOW))
}

fn floor_local(local: &LocalDateTime, grain: Grain) -> LocalDateTime {
    let mut floored: LocalDateTime = *local;
    floored.microsecond = 0;
    if grain >= Grain::Minute {
        floored.second = 0;
    }
    if grain >= Grain::Hour {
        floored.minute = 0;
    }
    if grain >= Grain::Day {
        floored.hour = 0;
    }
    if grain >= Grain::Month {
        floored.date.day = 1;
    }
    if grain == Grain::Year {
        floored.date.month = 1;
    }
    floored
}

/// The aligned value at or before `value`; without a grain a timestamp is only copied.
pub(crate) fn floor_scalar(value: &Scalar, grain: Option<Grain>) -> Scalar {
    match (&value.value, grain) {
        (ScalarValue::Integer(_), _) => value.clone(),
        (ScalarValue::Date(date), Some(grain)) if grain >= Grain::Month => {
            let month: u32 = if grain == Grain::Year { 1 } else { date.month };
            fresh(ScalarValue::Date(CivilDate {
                year: date.year,
                month,
                day: 1,
            }))
        }
        (ScalarValue::Date(_), _) => value.clone(),
        (ScalarValue::Timestamp(timestamp), None) => {
            retimed(timestamp, timestamp.local, timestamp.fold)
        }
        (ScalarValue::Timestamp(timestamp), Some(grain)) => retimed(
            timestamp,
            floor_local(&timestamp.local, grain),
            timestamp.fold,
        ),
    }
}

/// `value.replace(year=..., month=..., day=1)` `steps` months after the value's month.
fn advance_months(date: CivilDate, steps: i64) -> Result<CivilDate, CursorError> {
    let index: i64 = date.year * MONTHS_PER_YEAR + i64::from(date.month) - 1 + steps;
    let month: u32 = (index.rem_euclid(MONTHS_PER_YEAR) + 1) as u32;
    checked_date(index.div_euclid(MONTHS_PER_YEAR), month, 1)
}

/// The value one grain after an aligned `value`; without a grain dates step a day.
pub(crate) fn advance_scalar(value: &Scalar, grain: Option<Grain>) -> Result<Scalar, CursorError> {
    match &value.value {
        ScalarValue::Integer(number) => Ok(fresh(ScalarValue::Integer(integer_sum(*number, 1)?))),
        ScalarValue::Date(date) => {
            let advanced: CivilDate = match grain {
                Some(Grain::Month) => advance_months(*date, 1)?,
                Some(Grain::Year) => checked_date(date.year + 1, 1, 1)?,
                _ => add_days(*date, 1)?,
            };
            Ok(fresh(ScalarValue::Date(advanced)))
        }
        ScalarValue::Timestamp(timestamp) => {
            let local: &LocalDateTime = &timestamp.local;
            let Some(grain) = grain else {
                return Err(CursorError::Type(NO_GRAIN_STEP.to_owned()));
            };
            let Some(step) = fixed_step(grain) else {
                let date: CivilDate = match grain {
                    Grain::Month => advance_months(local.date, 1)?,
                    _ => checked_date(local.date.year + 1, 1, 1)?,
                };
                let advanced = LocalDateTime { date, ..*local };
                return Ok(retimed(timestamp, advanced, timestamp.fold));
            };
            Ok(retimed(timestamp, add_micros(local, step)?, false))
        }
    }
}

/// The value `steps` grains after an aligned `value`, in constant time.
pub(crate) fn advance_scalar_by(
    value: &Scalar,
    grain: Option<Grain>,
    steps: i64,
) -> Result<Scalar, CursorError> {
    if let ScalarValue::Integer(number) = &value.value {
        return Ok(fresh(ScalarValue::Integer(integer_sum(
            *number,
            i128::from(steps),
        )?)));
    }
    let Some(grain) = grain else {
        return Err(algebra(TEMPORAL_VALUES_NEED_GRAIN));
    };
    match &value.value {
        ScalarValue::Date(date) => Ok(fresh(ScalarValue::Date(match grain {
            Grain::Month => advance_months(*date, steps)?,
            Grain::Year => checked_date(date.year + steps, date.month, date.day)?,
            _ => add_days(
                *date,
                timedelta_days(timedelta_micros(i128::from(steps) * MICROS_PER_DAY)?),
            )?,
        }))),
        ScalarValue::Timestamp(timestamp) => {
            let local: &LocalDateTime = &timestamp.local;
            let Some(step) = fixed_step(grain) else {
                let date: CivilDate = match grain {
                    Grain::Month => advance_months(local.date, steps)?,
                    _ => checked_date(local.date.year + steps, local.date.month, local.date.day)?,
                };
                let advanced = LocalDateTime { date, ..*local };
                return Ok(retimed(timestamp, advanced, timestamp.fold));
            };
            let delta: i128 = timedelta_micros(step * i128::from(steps))?;
            Ok(retimed(timestamp, add_micros(local, delta)?, false))
        }
        ScalarValue::Integer(_) => Ok(value.clone()),
    }
}

/// An inclusive or exclusive bound moved one compatible unit in `direction`.
pub(crate) fn shift_bound(
    value: &Scalar,
    grain: Option<Grain>,
    direction: i64,
    missing_grain: &str,
) -> Result<Scalar, CursorError> {
    if let ScalarValue::Integer(number) = &value.value {
        return Ok(fresh(ScalarValue::Integer(integer_sum(
            *number,
            i128::from(direction),
        )?)));
    }
    let Some(grain) = grain else {
        return Err(algebra(missing_grain));
    };
    match &value.value {
        ScalarValue::Date(date) => Ok(fresh(ScalarValue::Date(add_days(
            *date,
            i128::from(direction),
        )?))),
        ScalarValue::Timestamp(timestamp) => {
            let step: i128 = fixed_step(grain).unwrap_or(MICROS_PER_DAY);
            let local: LocalDateTime = add_micros(&timestamp.local, i128::from(direction) * step)?;
            Ok(retimed(timestamp, local, false))
        }
        ScalarValue::Integer(_) => Ok(value.clone()),
    }
}
