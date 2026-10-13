//! Microsecond distances between UTC wall times.

use sqlbuild_cursor::algebra::models::{CivilDate, LocalDateTime};

use crate::freshness::constants::{
    DAYS_PER_ERA, DAYS_PER_YEAR, ERA_YEARS, FEBRUARY, MARCH_BASED_MONTH_DAYS, MICROS_PER_SECOND,
    MONTH_LENGTH_DIVISOR, MONTHS_FROM_MARCH, SECONDS_PER_DAY, SECONDS_PER_HOUR, SECONDS_PER_MINUTE,
};

/// Days since 0000-03-01 in the proleptic Gregorian calendar.
fn day_number(date: &CivilDate) -> i128 {
    let shifted: bool = date.month <= FEBRUARY;
    let year: i128 = i128::from(date.year) - i128::from(shifted);
    let era: i128 = year.div_euclid(ERA_YEARS);
    let year_of_era: i128 = year - era * ERA_YEARS;
    let month: i128 = i128::from(date.month);
    let month_from_march: i128 = if shifted {
        month + MONTHS_FROM_MARCH
    } else {
        month - 3
    };
    let day_of_year: i128 = (MARCH_BASED_MONTH_DAYS * month_from_march + 2) / MONTH_LENGTH_DIVISOR
        + i128::from(date.day)
        - 1;
    let day_of_era: i128 =
        year_of_era * DAYS_PER_YEAR + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * DAYS_PER_ERA + day_of_era
}

fn micros_of_day(local: &LocalDateTime) -> i128 {
    let seconds: u128 = u128::from(local.hour) * SECONDS_PER_HOUR
        + u128::from(local.minute) * SECONDS_PER_MINUTE
        + u128::from(local.second);
    (seconds * MICROS_PER_SECOND + u128::from(local.microsecond)) as i128
}

/// `later - earlier` in microseconds, as subtracting two `datetime` values gives it.
pub(crate) fn elapsed_micros(earlier: &LocalDateTime, later: &LocalDateTime) -> i128 {
    let days: i128 = day_number(&later.date) - day_number(&earlier.date);
    days * (SECONDS_PER_DAY * MICROS_PER_SECOND) as i128 + micros_of_day(later)
        - micros_of_day(earlier)
}
