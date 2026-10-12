//! Configuration values read from TOML and YAML, with the value domain of Python's `tomllib`.

use crate::constants::{
    DECIMAL_BASE, FEBRUARY, MAX_HOUR, MAX_MICROSECOND, MAX_MINUTE, MAX_SECOND, MAX_YEAR, MIN_YEAR,
    MONTHS_PER_YEAR,
};

/// A calendar date, Python's `datetime.date`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct ConfigDate {
    pub year: u16,
    pub month: u8,
    pub day: u8,
}

/// A time of day with microseconds, Python's naive `datetime.time`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct ConfigTime {
    pub hour: u8,
    pub minute: u8,
    pub second: u8,
    pub microsecond: u32,
}

/// A date and time, Python's `datetime.datetime`, with its UTC offset in seconds when aware.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct ConfigDateTime {
    pub date: ConfigDate,
    pub time: ConfigTime,
    pub utc_offset_seconds: Option<i32>,
}

impl ConfigDate {
    /// The date, or `None` where Python's `datetime.date` constructor raises.
    pub fn checked(year: i64, month: i64, day: i64) -> Option<Self> {
        let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
        let month_days = match month {
            FEBRUARY => 28 + i64::from(leap),
            4 | 6 | 9 | 11 => 30,
            _ => 31,
        };
        let valid = (MIN_YEAR..=MAX_YEAR).contains(&year)
            && (1..=MONTHS_PER_YEAR).contains(&month)
            && (1..=month_days).contains(&day);
        valid.then_some(Self {
            year: year as u16,
            month: month as u8,
            day: day as u8,
        })
    }
}

impl ConfigTime {
    /// The time, or `None` where Python's `datetime.time` constructor raises.
    pub fn checked(hour: i64, minute: i64, second: i64, microsecond: i64) -> Option<Self> {
        let valid = (0..=MAX_HOUR).contains(&hour)
            && (0..=MAX_MINUTE).contains(&minute)
            && (0..=MAX_SECOND).contains(&second)
            && (0..=MAX_MICROSECOND).contains(&microsecond);
        valid.then_some(Self {
            hour: hour as u8,
            minute: minute as u8,
            second: second as u8,
            microsecond: microsecond as u32,
        })
    }
}

/// One loaded configuration value; mappings keep document order and Python key equality.
#[derive(Clone, Debug, PartialEq)]
pub enum ConfigValue {
    Null,
    Bool(bool),
    Integer(i64),
    BigInteger(String),
    Float(f64),
    String(String),
    Date(ConfigDate),
    DateTime(ConfigDateTime),
    Time(ConfigTime),
    List(Vec<ConfigValue>),
    Map(Vec<(ConfigValue, ConfigValue)>),
}

impl ConfigValue {
    /// The entries of a mapping, or `None` for any other value.
    pub fn as_map(&self) -> Option<&[(ConfigValue, ConfigValue)]> {
        match self {
            Self::Map(entries) => Some(entries),
            _ => None,
        }
    }

    /// The value of a string key in a mapping, as Python's `mapping.get(key)` finds it.
    pub fn get(&self, key: &str) -> Option<&ConfigValue> {
        self.as_map()?
            .iter()
            .find(|(candidate, _)| matches!(candidate, Self::String(text) if text == key))
            .map(|(_, value)| value)
    }
}

/// The content of one composed YAML node; aliases share node ids.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ComposedYamlContent {
    Scalar(String),
    Sequence(Vec<usize>),
    Mapping(Vec<(usize, usize)>),
}

impl ComposedYamlContent {
    /// The value of a scalar node.
    pub fn as_scalar(&self) -> Option<&str> {
        match self {
            Self::Scalar(value) => Some(value),
            Self::Sequence(_) | Self::Mapping(_) => None,
        }
    }
}

/// One composed YAML node, with the char indices where its source text starts and ends.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ComposedYamlNode {
    pub content: ComposedYamlContent,
    pub start: usize,
    pub end: usize,
}

/// The composed node graph of one YAML document; `root` is `None` for an empty stream.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ComposedYaml {
    pub nodes: Vec<ComposedYamlNode>,
    pub root: Option<usize>,
}

/// An exact non-negative integer: its decimal digit values, least significant first.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct Natural {
    digits: Vec<u32>,
}

impl Natural {
    /// The integer of decimal digit values, most significant first.
    pub(crate) fn from_digit_values(values: impl DoubleEndedIterator<Item = u32>) -> Self {
        Self {
            digits: values.rev().collect(),
        }
        .trimmed()
    }

    fn trimmed(mut self) -> Self {
        while self.digits.last() == Some(&0) {
            self.digits.pop();
        }
        self
    }

    /// Whether the integer is zero.
    pub(crate) fn is_zero(&self) -> bool {
        self.digits.is_empty()
    }

    /// `self * factor + addend`.
    pub(crate) fn times_plus(&self, factor: u32, addend: u32) -> Self {
        let base = u64::from(DECIMAL_BASE);
        let mut carry = u64::from(addend);
        let mut digits: Vec<u32> = Vec::with_capacity(self.digits.len() + 2);
        for digit in &self.digits {
            let value = u64::from(*digit) * u64::from(factor) + carry;
            digits.push((value % base) as u32);
            carry = value / base;
        }
        while carry > 0 {
            digits.push((carry % base) as u32);
            carry /= base;
        }
        Self { digits }.trimmed()
    }

    /// `self + other`.
    pub(crate) fn plus(&self, other: &Self) -> Self {
        let mut carry = 0;
        let mut digits: Vec<u32> = Vec::new();
        for index in 0..self.digits.len().max(other.digits.len()) {
            let sum = self.digits.get(index).copied().unwrap_or_default()
                + other.digits.get(index).copied().unwrap_or_default()
                + carry;
            digits.push(sum % DECIMAL_BASE);
            carry = sum / DECIMAL_BASE;
        }
        digits.push(carry);
        Self { digits }.trimmed()
    }

    /// The decimal digits, `"0"` for zero.
    pub(crate) fn decimal(&self) -> String {
        if self.is_zero() {
            return "0".to_owned();
        }
        self.digits
            .iter()
            .rev()
            .filter_map(|digit| char::from_digit(*digit, DECIMAL_BASE))
            .collect()
    }
}
