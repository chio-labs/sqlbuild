//! The code order of a validated rule catalogue and its configured options.

use std::collections::{BTreeMap, BTreeSet};

use crate::rule_catalogue::_helpers::options::{
    has_value_type, is_instance, plain_integer, python_equal,
};
use crate::rule_catalogue::models::{CatalogueRule, OptionSpec, OptionValue};

/// Indices of `rules` sorted by code, or the first `RulesError` message the catalogue raises.
pub fn sorted_catalogue_order(
    rules: &[CatalogueRule],
    configured: &BTreeMap<String, BTreeMap<String, OptionValue>>,
) -> Result<Vec<usize>, String> {
    let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
    for rule in rules {
        *counts.entry(rule.code.as_str()).or_default() += 1;
    }
    let duplicates: Vec<&str> = counts
        .iter()
        .filter(|(_, count)| **count > 1)
        .map(|(code, _)| *code)
        .collect();
    if !duplicates.is_empty() {
        return Err(format!("duplicate rule codes: {}", duplicates.join(", ")));
    }
    let empty: BTreeMap<String, OptionValue> = BTreeMap::new();
    for rule in rules {
        validate_options(rule, configured.get(&rule.code).unwrap_or(&empty))?;
    }
    let unknown: Vec<&str> = configured
        .keys()
        .map(String::as_str)
        .filter(|code| !counts.contains_key(code))
        .collect();
    if !unknown.is_empty() {
        return Err(format!(
            "rule options target unknown codes: {}",
            unknown.join(", ")
        ));
    }
    let mut order: Vec<usize> = (0..rules.len()).collect();
    order.sort_by(|left, right| rules[*left].code.cmp(&rules[*right].code));
    Ok(order)
}

fn validate_options(
    rule: &CatalogueRule,
    configured: &BTreeMap<String, OptionValue>,
) -> Result<(), String> {
    let code: &str = &rule.code;
    for option in &rule.options {
        validate_declaration(code, option)?;
    }
    let declared: BTreeMap<&str, &OptionSpec> = rule
        .options
        .iter()
        .map(|option| (option.name.as_str(), option))
        .collect();
    let unknown: BTreeSet<&str> = configured
        .keys()
        .map(String::as_str)
        .filter(|name| !declared.contains_key(name))
        .collect();
    if !unknown.is_empty() {
        let names: Vec<&str> = unknown.into_iter().collect();
        return Err(format!(
            "rule {code} has unknown options: {}",
            names.join(", ")
        ));
    }
    for (name, value) in configured {
        let Some(option) = declared.get(name.as_str()) else {
            continue;
        };
        if !has_value_type(value, &option.value_type) {
            return Err(format!("rule {code} option {name} has the wrong type"));
        }
        if !option.choices.is_empty() && !option.choices.iter().any(|c| python_equal(c, value)) {
            return Err(format!(
                "rule {code} option {name} is not an allowed choice"
            ));
        }
        if let OptionValue::Tuple(items) = value {
            if option
                .minimum_items
                .is_some_and(|minimum| (items.len() as i64) < minimum)
            {
                return Err(format!("rule {code} option {name} has too few items"));
            }
            if let Some(item_type) = &option.item_type
                && items.iter().any(|item| !is_instance(item, item_type))
            {
                return Err(format!(
                    "rule {code} option {name} has item values of the wrong type"
                ));
            }
        }
        if let Some(integer) = plain_integer(value) {
            if option.minimum.is_some_and(|minimum| integer < minimum) {
                return Err(format!("rule {code} option {name} is below its minimum"));
            }
            if option.maximum.is_some_and(|maximum| integer > maximum) {
                return Err(format!("rule {code} option {name} exceeds its maximum"));
            }
        }
    }
    Ok(())
}

fn validate_declaration(code: &str, option: &OptionSpec) -> Result<(), String> {
    let name: &str = &option.name;
    if option.name.trim().is_empty() || option.description.trim().is_empty() {
        return Err(format!("rule {code} declares an incomplete option"));
    }
    let default: &OptionValue = &option.default;
    if !has_value_type(default, &option.value_type) {
        return Err(format!(
            "rule {code} option {name} has a default of the wrong type"
        ));
    }
    if !option.choices.is_empty() && !option.choices.iter().any(|c| python_equal(c, default)) {
        return Err(format!(
            "rule {code} option {name} default is not an allowed choice"
        ));
    }
    if let OptionValue::Tuple(items) = default {
        if option
            .minimum_items
            .is_some_and(|minimum| (items.len() as i64) < minimum)
        {
            return Err(format!(
                "rule {code} option {name} default has too few items"
            ));
        }
        if let Some(item_type) = &option.item_type
            && items.iter().any(|item| !is_instance(item, item_type))
        {
            return Err(format!(
                "rule {code} option {name} default has items of the wrong type"
            ));
        }
    }
    if let Some(integer) = plain_integer(default) {
        if option.minimum.is_some_and(|minimum| integer < minimum) {
            return Err(format!(
                "rule {code} option {name} default is below its minimum"
            ));
        }
        if option.maximum.is_some_and(|maximum| integer > maximum) {
            return Err(format!(
                "rule {code} option {name} default exceeds its maximum"
            ));
        }
    }
    Ok(())
}
