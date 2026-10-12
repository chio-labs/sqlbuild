//! Source freshness: strategy inference, value kinds from declared types, and duration checks.

use sqlbuild_core::text::main::decimal_digit_value::decimal_digit_value;
use sqlbuild_core::text::main::is_decimal_digit::is_decimal_digit;
use sqlbuild_core::text::main::python_casefold::python_casefold;
use sqlbuild_core::text::main::python_isalnum::python_isalnum;
use sqlbuild_core::text::main::python_isdigit::python_isdigit;
use sqlbuild_core::text::main::python_isspace::python_isspace;
use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::types::{AuthoredNode, NodeKind};

use crate::yaml_entries::_helpers::fields::{
    Site, get, optional_mapping, optional_text, reject_unknown_keys,
};
use crate::yaml_entries::models::{ParsedAgePolicy, ParsedFreshness, ParsedYamlColumn};

const FRESHNESS_KEYS: [&str; 7] = [
    "age_policy",
    "column",
    "filter",
    "lag_tolerance",
    "query",
    "strategy",
    "type",
];
const AGE_POLICY_KEYS: [&str; 2] = ["error_after", "warn_after"];
const STRATEGIES: [&str; 3] = ["adapter", "column", "sql"];
const VALUE_KINDS: [&str; 3] = ["integer", "string", "timestamp"];
const TIMESTAMP: &str = "timestamp";
const INTEGER: &str = "integer";
const STRING: &str = "string";
const ADAPTER: &str = "adapter";
const COLUMN: &str = "column";
const SQL: &str = "sql";
const TIMESTAMP_TYPES: [&str; 9] = [
    "DATETIME",
    "DATETIME2",
    "DATETIMEOFFSET",
    "SMALLDATETIME",
    "TIMESTAMP",
    "TIMESTAMPTZ",
    "TIMESTAMP_LTZ",
    "TIMESTAMP_NTZ",
    "TIMESTAMP_TZ",
];
const TIMESTAMP_ZONE_PREFIXES: [&str; 2] =
    ["TIMESTAMP WITH TIME ZONE", "TIMESTAMP WITHOUT TIME ZONE"];
const INTEGER_TYPES: [&str; 9] = [
    "BIGINT", "INT", "INT2", "INT4", "INT8", "INT64", "INTEGER", "SMALLINT", "TINYINT",
];
const STRING_TYPES: [&str; 8] = [
    "CHAR",
    "CHARACTER",
    "CHARACTER VARYING",
    "NCHAR",
    "NVARCHAR",
    "STRING",
    "TEXT",
    "VARCHAR",
];
/// Duration units in `Duration._PATTERN` order, and the seconds each fixed unit spans.
const DURATION_UNITS: [(&str, u128); 6] = [
    ("y", 0),
    ("mo", 0),
    ("d", 86_400),
    ("h", 3_600),
    ("m", 60),
    ("s", 1),
];
/// The units source freshness durations may use: minutes, hours and days.
const FRESHNESS_UNITS: [&str; 3] = ["m", "h", "d"];

fn one_of(value: &str, allowed: &[&'static str]) -> Option<&'static str> {
    allowed.iter().copied().find(|item| *item == value)
}

/// `_optional_freshness_config`.
pub(crate) fn freshness<N: AuthoredNode>(
    entries: &[(N, N)],
    columns: &[ParsedYamlColumn<N>],
    path: &str,
) -> Result<Option<ParsedFreshness<N>>, ConfigError> {
    let raw: N = match get(entries, "freshness") {
        None => return Ok(None),
        Some(value) if value.kind() == NodeKind::Null => return Ok(None),
        Some(value) => value.clone(),
    };
    if raw.kind() != NodeKind::Map {
        return Err(ConfigError::compile(format!(
            "{path} source 'freshness' must be a mapping"
        )));
    }
    let freshness: Vec<(N, N)> = raw.entries();
    let site: Site<'_> = Site {
        path,
        label: "source freshness",
    };
    reject_unknown_keys(&freshness, &FRESHNESS_KEYS, site)?;
    let raw_strategy: Option<String> =
        optional_text(&freshness, "strategy", site)?.and_then(|node| node.text());
    let strategy: Option<&'static str> = match &raw_strategy {
        None => None,
        Some(text) => Some(one_of(text, &STRATEGIES).ok_or_else(|| {
            site.error(&format!(
                "'strategy' must be one of: {}",
                STRATEGIES.join(", ")
            ))
        })?),
    };
    let mut value_kind: Option<&'static str> =
        match optional_text(&freshness, "type", site)?.and_then(|node| node.text()) {
            None => None,
            Some(text) => Some(one_of(&text, &VALUE_KINDS).ok_or_else(|| {
                site.error(&format!(
                    "'type' must be one of: {}",
                    VALUE_KINDS.join(", ")
                ))
            })?),
        };
    let column: Option<N> = optional_text(&freshness, "column", site)?;
    let query: Option<N> = optional_text(&freshness, "query", site)?;
    let filter: Option<N> = optional_text(&freshness, "filter", site)?;
    let lag_tolerance: Option<N> = optional_text(&freshness, "lag_tolerance", site)?;
    let age_policy: Option<ParsedAgePolicy<N>> = age_policy(&freshness, path)?;
    let strategy: &'static str = match strategy {
        Some(strategy) => strategy,
        None => implied_strategy(
            (column.is_some(), query.is_some()),
            value_kind.is_some() || filter.is_some(),
            path,
        )?,
    };
    if strategy == COLUMN
        && let Some(column_name) = column.as_ref().and_then(AuthoredNode::text)
    {
        value_kind = column_value_kind(&column_name, value_kind, columns, path)?;
    }
    let parsed: ParsedFreshness<N> = ParsedFreshness {
        strategy,
        value_kind,
        column,
        query,
        filter,
        lag_tolerance,
        age_policy,
    };
    validate(&parsed, path)?;
    Ok(Some(parsed))
}

fn implied_strategy(
    (has_column, has_query): (bool, bool),
    has_type_or_filter: bool,
    path: &str,
) -> Result<&'static str, ConfigError> {
    if has_column && has_query {
        return Err(ConfigError::compile(format!(
            "{path} source freshness cannot set both column and query; set strategy or remove \
             one of them"
        )));
    }
    if has_column {
        return Ok(COLUMN);
    }
    if has_query {
        return Ok(SQL);
    }
    if has_type_or_filter {
        return Err(ConfigError::compile(format!(
            "{path} source freshness type and filter require column or query"
        )));
    }
    Ok(ADAPTER)
}

fn age_policy<N: AuthoredNode>(
    freshness: &[(N, N)],
    path: &str,
) -> Result<Option<ParsedAgePolicy<N>>, ConfigError> {
    if get(freshness, "age_policy").is_none() {
        return Ok(None);
    }
    let site: Site<'_> = Site {
        path,
        label: "source freshness",
    };
    let policy: Vec<(N, N)> = optional_mapping(freshness, "age_policy", site)?
        .map(|node| node.entries())
        .unwrap_or_default();
    let site: Site<'_> = Site {
        path,
        label: "source freshness age_policy",
    };
    reject_unknown_keys(&policy, &AGE_POLICY_KEYS, site)?;
    let warn_after: Option<N> = optional_text(&policy, "warn_after", site)?;
    let error_after: Option<N> = optional_text(&policy, "error_after", site)?;
    if warn_after.is_none() && error_after.is_none() {
        return Err(site.error("requires warn_after or error_after"));
    }
    Ok(Some(ParsedAgePolicy {
        warn_after,
        error_after,
    }))
}

/// `_resolve_column_freshness_value_kind`.
fn column_value_kind<N: AuthoredNode>(
    column: &str,
    explicit: Option<&'static str>,
    columns: &[ParsedYamlColumn<N>],
    path: &str,
) -> Result<Option<&'static str>, ConfigError> {
    let declared_type: Option<String> = find_column(columns, column)
        .and_then(|declared| declared.column_type.as_ref())
        .and_then(AuthoredNode::text);
    let inferred: Option<&'static str> = declared_type.as_deref().and_then(type_value_kind);
    let Some(explicit) = explicit else {
        if inferred.is_none()
            && let Some(declared_type) = &declared_type
        {
            return Err(ConfigError::compile(format!(
                "{path} source freshness cannot infer type from column '{column}' declared as \
                 {declared_type}; set type to timestamp, integer, or string"
            )));
        }
        return Ok(inferred);
    };
    if let Some(inferred) = inferred
        && inferred != explicit
    {
        return Err(ConfigError::compile(format!(
            "{path} source freshness type {explicit} contradicts column '{column}' declared as \
             {}; remove type or set it to {inferred}",
            declared_type.unwrap_or_default()
        )));
    }
    Ok(Some(explicit))
}

/// `_find_source_column`: the exact name, else the only case-insensitive match.
fn find_column<'a, N: AuthoredNode>(
    columns: &'a [ParsedYamlColumn<N>],
    name: &str,
) -> Option<&'a ParsedYamlColumn<N>> {
    if let Some(exact) = columns.iter().find(|column| column.name.is_text(name)) {
        return Some(exact);
    }
    let folded: String = python_casefold(name);
    let matches: Vec<&ParsedYamlColumn<N>> = columns
        .iter()
        .filter(|column| {
            column
                .name
                .text()
                .is_some_and(|text| python_casefold(&text) == folded)
        })
        .collect();
    match matches.as_slice() {
        [only] => Some(only),
        _ => None,
    }
}

/// `_freshness_value_kind_for_type`.
fn type_value_kind(type_sql: &str) -> Option<&'static str> {
    let upper: String = type_sql.to_uppercase();
    let normalized: String = upper
        .split(python_isspace)
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
    let base: &str = python_strip(normalized.split('(').next().unwrap_or_default());
    if TIMESTAMP_TYPES.contains(&base)
        || TIMESTAMP_ZONE_PREFIXES
            .iter()
            .any(|prefix| normalized.starts_with(prefix))
    {
        return Some(TIMESTAMP);
    }
    if INTEGER_TYPES.contains(&base) {
        return Some(INTEGER);
    }
    STRING_TYPES.contains(&base).then_some(STRING)
}

/// `_validate_freshness_config`.
fn validate<N: AuthoredNode>(config: &ParsedFreshness<N>, path: &str) -> Result<(), ConfigError> {
    let error = |text: &str| ConfigError::compile(format!("{path} source freshness {text}"));
    if let Some(lag_tolerance) = &config.lag_tolerance {
        if config.value_kind != Some(TIMESTAMP) {
            return Err(error("lag_tolerance requires type timestamp"));
        }
        if freshness_minutes(&lag_tolerance.text().unwrap_or_default()).is_none() {
            return Err(error(
                "lag_tolerance must be a positive duration like 15m, 2h, or 1d",
            ));
        }
    }
    if let Some(policy) = &config.age_policy {
        if config.strategy != ADAPTER && config.value_kind != Some(TIMESTAMP) {
            return Err(error("age_policy requires type timestamp"));
        }
        let warn: Option<String> = policy.warn_after.as_ref().and_then(AuthoredNode::text);
        let fail: Option<String> = policy.error_after.as_ref().and_then(AuthoredNode::text);
        for raw in [&warn, &fail].into_iter().flatten() {
            if freshness_minutes(raw).is_none() {
                return Err(error(
                    "age_policy values must be positive durations like 15m, 2h, or 1d",
                ));
            }
        }
        if let (Some(warn), Some(fail)) = (&warn, &fail)
            && freshness_minutes(warn) > freshness_minutes(fail)
        {
            return Err(error(
                "age_policy warn_after must be less than or equal to error_after",
            ));
        }
    }
    match config.strategy {
        ADAPTER => {
            if config.value_kind.is_some()
                || config.column.is_some()
                || config.query.is_some()
                || config.filter.is_some()
            {
                return Err(error(
                    "strategy adapter does not support type, column, query, or filter",
                ));
            }
            Ok(())
        }
        COLUMN => {
            let Some(column) = config.column.as_ref().and_then(AuthoredNode::text) else {
                return Err(error("strategy column requires column"));
            };
            if !plain_column_name(&column) {
                return Err(error(
                    "column must be a plain column name; use strategy sql for expressions",
                ));
            }
            if config.value_kind.is_none() {
                return Err(error(
                    "strategy column requires type; set type or declare the column with a type \
                     under columns",
                ));
            }
            if config.query.is_some() {
                return Err(error("strategy column does not support query"));
            }
            Ok(())
        }
        _ => {
            if config.query.is_none() {
                return Err(error("strategy sql requires query"));
            }
            if config.value_kind.is_none() {
                return Err(error("strategy sql requires type"));
            }
            if config.column.is_some() {
                return Err(error("strategy sql does not support column"));
            }
            if config.filter.is_some() {
                return Err(error("strategy sql does not support filter"));
            }
            Ok(())
        }
    }
}

/// `column.replace("_", "").isalnum() and not column[0].isdigit()`.
fn plain_column_name(column: &str) -> bool {
    let rest: String = column.replace('_', "");
    let alphanumeric: bool = !rest.is_empty() && rest.chars().all(python_isalnum);
    let leading_digit: bool = column.chars().next().is_some_and(python_isdigit);
    alphanumeric && !leading_digit
}

/// The whole minutes of a source freshness duration: one non-zero minute, hour or day amount.
pub(crate) fn freshness_minutes(text: &str) -> Option<u128> {
    let text: &str = text.strip_suffix('\n').unwrap_or(text);
    let mut amounts: [u128; 6] = [0; 6];
    let mut next_unit: usize = 0;
    let mut rest: &str = text;
    while !rest.is_empty() {
        let digits: usize = rest
            .char_indices()
            .find(|(_, character)| !is_decimal_digit(*character))
            .map_or(rest.len(), |(at, _)| at);
        if digits == 0 {
            return None;
        }
        let unit: usize = (next_unit..DURATION_UNITS.len())
            .find(|index| rest[digits..].starts_with(DURATION_UNITS[*index].0))?;
        amounts[unit] = decimal_value(&rest[..digits]);
        rest = &rest[digits + DURATION_UNITS[unit].0.len()..];
        next_unit = unit + 1;
    }
    let used: Vec<usize> = (0..amounts.len())
        .filter(|index| amounts[*index] != 0)
        .collect();
    let [unit] = used.as_slice() else {
        return None;
    };
    let (name, seconds) = DURATION_UNITS[*unit];
    FRESHNESS_UNITS
        .contains(&name)
        .then(|| amounts[*unit].saturating_mul(seconds) / 60)
}

/// The value of Unicode decimal digits, saturating far beyond any real duration.
fn decimal_value(digits: &str) -> u128 {
    digits.chars().fold(0_u128, |value, character| {
        let digit: u128 = decimal_digit_value(character).map_or(0, u128::from);
        value.saturating_mul(10).saturating_add(digit)
    })
}
