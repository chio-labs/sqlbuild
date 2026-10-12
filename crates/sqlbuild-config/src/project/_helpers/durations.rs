//! `Duration.parse` and the duration properties the loaders check, over exact integers.

use crate::models::Natural;
use crate::project::constants::PYTHON_INT_MAX_STR_DIGITS;
use crate::project::errors::ConfigFailure;
use sqlbuild_core::text::main::decimal_digit_value::decimal_digit_value;

const UNITS: [&str; 6] = ["y", "mo", "d", "h", "m", "s"];
const DAY_INDEX: usize = 2;
const FIXED_UNIT_SECONDS: [u32; 4] = [86_400, 3_600, 60, 1];

/// A parsed non-zero duration.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Duration {
    amounts: [Natural; 6],
}

impl Duration {
    /// `has_calendar_component`: years or months are non-zero.
    pub(crate) fn has_calendar_component(&self) -> bool {
        self.amounts[..DAY_INDEX]
            .iter()
            .any(|amount| !amount.is_zero())
    }

    /// `units == {"d"}`.
    pub(crate) fn is_whole_days(&self) -> bool {
        self.amounts
            .iter()
            .enumerate()
            .all(|(index, amount)| (index == DAY_INDEX) != amount.is_zero())
    }

    /// The day amount in decimal digits.
    pub(crate) fn days(&self) -> String {
        self.amounts[DAY_INDEX].decimal()
    }

    /// `fixed_seconds`: days and smaller units as whole seconds.
    pub(crate) fn fixed_seconds(&self) -> Natural {
        let mut total = Natural::default();
        for (amount, seconds) in self.amounts[DAY_INDEX..].iter().zip(FIXED_UNIT_SECONDS) {
            total = total.plus(&amount.times_plus(seconds, 0));
        }
        total
    }
}

/// The leading run of Python decimal digits as an integer, its byte length and its digit count.
fn leading_digits(text: &str) -> (Natural, usize, usize) {
    let mut values: Vec<u32> = Vec::new();
    let mut length = 0;
    for character in text.chars() {
        let Some(value) = decimal_digit_value(character) else {
            break;
        };
        values.push(value);
        length += character.len_utf8();
    }
    let count = values.len();
    (
        Natural::from_digit_values(values.into_iter()),
        length,
        count,
    )
}

/// `Duration.parse(text)`, `None` when it does not match or is zero; `int()`'s digit limit raises.
pub(crate) fn parse_duration(text: &str) -> Result<Option<Duration>, ConfigFailure> {
    let mut rest: &str = text.strip_suffix('\n').unwrap_or(text);
    let mut amounts: [Natural; 6] = Default::default();
    let mut counts: [usize; 6] = [0; 6];
    let mut next_unit = 0;
    while !rest.is_empty() {
        let (amount, length, count) = leading_digits(rest);
        if length == 0 {
            return Ok(None);
        }
        let Some(unit) =
            (next_unit..UNITS.len()).find(|index| rest[length..].starts_with(UNITS[*index]))
        else {
            return Ok(None);
        };
        amounts[unit] = amount;
        counts[unit] = count;
        rest = &rest[length + UNITS[unit].len()..];
        next_unit = unit + 1;
    }
    if let Some(count) = counts
        .iter()
        .find(|count| **count > PYTHON_INT_MAX_STR_DIGITS)
    {
        return Err(ConfigFailure::integer_digits(*count));
    }
    let is_zero = amounts.iter().all(Natural::is_zero);
    Ok((!is_zero).then_some(Duration { amounts }))
}
