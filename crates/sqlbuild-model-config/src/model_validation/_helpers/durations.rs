//! `Duration.parse` for ASCII text; other text is left to Python.

use crate::model_validation::constants::DAY_UNIT_INDEX;
use crate::model_validation::models::Rejected;

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

/// Return `Duration.parse(text)`: a duration, `None` when it does not parse, or a rejection.
pub(crate) fn parse_duration(text: &str) -> Result<Option<Duration>, Rejected> {
    if !text.is_ascii() || text.contains('\n') {
        return Err(Rejected);
    }
    let mut amounts = [0_u128; 6];
    let mut next_unit = 0;
    let mut rest = text;
    while !rest.is_empty() {
        let digits = rest.bytes().take_while(u8::is_ascii_digit).count();
        if digits == 0 {
            return Ok(None);
        }
        let amount: u128 = rest[..digits].parse().map_err(|_| Rejected)?;
        rest = &rest[digits..];
        let Some(unit) = (next_unit..UNITS.len()).find(|index| rest.starts_with(UNITS[*index]))
        else {
            return Ok(None);
        };
        amounts[unit] = amount;
        rest = &rest[UNITS[unit].len()..];
        next_unit = unit + 1;
    }
    let total_months = amounts[0]
        .checked_mul(MONTHS_PER_YEAR)
        .and_then(|months| months.checked_add(amounts[1]))
        .ok_or(Rejected)?;
    let fixed_seconds = amounts[DAY_UNIT_INDEX..]
        .iter()
        .zip(UNIT_SECONDS)
        .try_fold(0_u128, |total, (amount, seconds)| {
            amount
                .checked_mul(seconds)
                .and_then(|value| total.checked_add(value))
        })
        .ok_or(Rejected)?;
    if total_months == 0 && fixed_seconds == 0 {
        return Ok(None);
    }
    Ok(Some(Duration {
        total_months,
        fixed_seconds,
        amounts,
    }))
}
