//! `Duration.parse`: `^(?:(\d+)y)?(?:(\d+)mo)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$`.

use sqlbuild_core::text::main::is_python_decimal::is_python_decimal;
use sqlbuild_core::text::models::PythonText;

use crate::model_validation::constants::{DAY_UNIT_INDEX, MAX_DURATION_AMOUNT};
use crate::model_validation::errors::DurationNumberError;

const MONTHS_PER_YEAR: u128 = 12;
const UNIT_SECONDS: [u128; 4] = [86_400, 3_600, 60, 1];
const UNITS: [&str; 6] = ["y", "mo", "d", "h", "m", "s"];

/// A parsed non-zero duration.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Duration {
    /// Years folded into months.
    pub(crate) total_months: u128,
    /// Days and smaller units as whole seconds.
    pub(crate) fixed_seconds: u128,
    /// Amounts by unit, in `UNITS` order.
    amounts: [u128; 6],
}

impl Duration {
    /// Return whether only days are non-zero, like `units == {"d"}`.
    pub(crate) fn is_whole_days(&self) -> bool {
        self.amounts
            .iter()
            .enumerate()
            .all(|(index, amount)| (index == DAY_UNIT_INDEX) == (*amount != 0))
    }

    /// Return the day amount.
    pub(crate) fn days(&self) -> u128 {
        self.amounts[DAY_UNIT_INDEX]
    }
}

/// `Duration.parse(text)`, `None` when it does not parse, or why the duration is rejected.
pub(crate) fn parse_duration(
    python: PythonText,
    text: &str,
) -> Result<Option<Duration>, DurationNumberError> {
    let text: &str = text.strip_suffix('\n').unwrap_or(text);
    let is_digit = |character: char| is_python_decimal(python, character);
    let mut amounts = [0_u128; 6];
    let mut next_unit = 0;
    let mut rest = text;
    let mut non_ascii = false;
    while !rest.is_empty() {
        let digits: usize = rest
            .char_indices()
            .find(|(_, character)| !is_digit(*character))
            .map_or(rest.len(), |(at, _)| at);
        if digits == 0 {
            return Ok(None);
        }
        let Some(unit) =
            (next_unit..UNITS.len()).find(|index| rest[digits..].starts_with(UNITS[*index]))
        else {
            return Ok(None);
        };
        non_ascii |= !rest[..digits].is_ascii();
        amounts[unit] = bounded_amount(&rest[..digits]);
        rest = &rest[digits + UNITS[unit].len()..];
        next_unit = unit + 1;
    }
    if non_ascii {
        return Err(DurationNumberError::NonAsciiDigits);
    }
    if amounts.contains(&u128::MAX) {
        return Err(DurationNumberError::TooLarge);
    }
    let total_months = amounts[0] * MONTHS_PER_YEAR + amounts[1];
    let fixed_seconds = amounts[DAY_UNIT_INDEX..]
        .iter()
        .zip(UNIT_SECONDS)
        .map(|(amount, seconds)| amount * seconds)
        .sum();
    if total_months == 0 && fixed_seconds == 0 {
        return Ok(None);
    }
    Ok(Some(Duration {
        total_months,
        fixed_seconds,
        amounts,
    }))
}

/// The amount `digits` spell, or `u128::MAX` when it is not ASCII or exceeds a signed 64-bit integer.
fn bounded_amount(digits: &str) -> u128 {
    match digits.parse::<u128>() {
        Ok(amount) if amount <= MAX_DURATION_AMOUNT => amount,
        Ok(_) | Err(_) => u128::MAX,
    }
}
