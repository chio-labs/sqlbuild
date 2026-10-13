//! The capture time of a snapshot, as `YYYY-MM-DDTHH:MM:SSZ`.

use crate::scenario_command::constants::{
    DAYS_PER_ERA, EPOCH_DAY_OFFSET, FEBRUARY, MARCH_BASED_JANUARY, SECONDS_PER_DAY, YEARS_PER_ERA,
};

/// The proleptic Gregorian `(year, month, day)` of days since 1970-01-01 (Hinnant's algorithm).
fn civil_date(days: i64) -> (i64, i64, i64) {
    let shifted: i64 = days + EPOCH_DAY_OFFSET;
    let era: i64 = shifted.div_euclid(DAYS_PER_ERA);
    let day_of_era: i64 = shifted.rem_euclid(DAYS_PER_ERA);
    let year_of_era: i64 =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year: i64 = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_index: i64 = (5 * day_of_year + 2) / 153;
    let day: i64 = day_of_year - (153 * month_index + 2) / 5 + 1;
    let month: i64 = if month_index < MARCH_BASED_JANUARY {
        month_index + 3
    } else {
        month_index - 9
    };
    (
        year_of_era + era * YEARS_PER_ERA + i64::from(month <= FEBRUARY),
        month,
        day,
    )
}

/// `datetime.now(UTC).replace(microsecond=0).isoformat()` with `+00:00` written as `Z`.
#[must_use]
pub fn format_captured_at(epoch_seconds: i64) -> String {
    let (year, month, day) = civil_date(epoch_seconds.div_euclid(SECONDS_PER_DAY));
    let of_day: i64 = epoch_seconds.rem_euclid(SECONDS_PER_DAY);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        of_day / 3_600,
        of_day % 3_600 / 60,
        of_day % 60
    )
}
