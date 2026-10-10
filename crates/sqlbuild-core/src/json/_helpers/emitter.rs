//! Serialize a [`JsonValue`] in the layout of one Python serializer.

use crate::json::_helpers::floats::{orjson_text, python_repr};
use crate::json::_helpers::strings::{StringEscaping, json_string, json_utf16_string};
use crate::json::constants::{
    ORJSON_MAX_CONTAINER_DEPTH, ORJSON_MAX_INTEGER, ORJSON_MIN_INTEGER, PYTHON_INT_MAX_STR_DIGITS,
    STDLIB_MAX_CONTAINER_DEPTH,
};
use crate::json::errors::JsonEmitError;
use crate::json::models::{JsonDialect, JsonInteger, JsonValue};

/// The resolved layout of one serializer configuration.
struct Layout<'options> {
    indent: Option<&'options str>,
    item_separator: &'options str,
    key_separator: &'options str,
    sort_keys: bool,
    escaping: StringEscaping,
    orjson: bool,
    allow_nan: bool,
}

impl<'options> Layout<'options> {
    fn new(dialect: &'options JsonDialect) -> Self {
        match dialect {
            JsonDialect::Stdlib(options) => Self {
                indent: options.indent.as_deref(),
                item_separator: &options.item_separator,
                key_separator: &options.key_separator,
                sort_keys: options.sort_keys,
                escaping: if options.ensure_ascii {
                    StringEscaping::Ascii
                } else {
                    StringEscaping::Unicode
                },
                orjson: false,
                allow_nan: options.allow_nan,
            },
            JsonDialect::Orjson(options) => Self {
                indent: options.indent_2.then_some("  "),
                item_separator: ",",
                key_separator: if options.indent_2 { ": " } else { ":" },
                sort_keys: options.sort_keys,
                escaping: StringEscaping::Unicode,
                orjson: true,
                allow_nan: true,
            },
        }
    }

    fn newline(&self, level: usize) -> String {
        self.indent
            .map_or_else(String::new, |indent| format!("\n{}", indent.repeat(level)))
    }

    fn integer(&self, value: &JsonInteger) -> Result<String, JsonEmitError> {
        let in_range = value
            .to_i128()
            .is_some_and(|number| (ORJSON_MIN_INTEGER..=ORJSON_MAX_INTEGER).contains(&number));
        if self.orjson && !in_range {
            return Err(JsonEmitError::IntegerOutOfRange);
        }
        let digits = value.as_str().trim_start_matches('-').len();
        if digits > PYTHON_INT_MAX_STR_DIGITS {
            return Err(JsonEmitError::IntegerTooLong);
        }
        Ok(value.as_str().to_owned())
    }

    fn float(&self, value: f64) -> Result<String, JsonEmitError> {
        match value {
            _ if value.is_finite() && self.orjson => Ok(orjson_text(value)),
            _ if value.is_finite() => Ok(python_repr(value)),
            _ if self.orjson => Ok("null".to_owned()),
            _ if !self.allow_nan => Err(JsonEmitError::NonFiniteFloat),
            _ if value.is_nan() => Ok("NaN".to_owned()),
            _ if value.is_sign_positive() => Ok("Infinity".to_owned()),
            _ => Ok("-Infinity".to_owned()),
        }
    }

    /// Whether the serializer refuses this container at `level`; orjson skips empty lists.
    fn too_deep(&self, value: &JsonValue, level: usize) -> bool {
        let counted: bool = match value {
            JsonValue::Object(_) => true,
            JsonValue::Array(items) => !self.orjson || !items.is_empty(),
            _ => false,
        };
        let limit: usize = if self.orjson {
            ORJSON_MAX_CONTAINER_DEPTH
        } else {
            STDLIB_MAX_CONTAINER_DEPTH
        };
        counted && level >= limit
    }

    fn value(&self, value: &JsonValue, level: usize) -> Result<String, JsonEmitError> {
        if self.too_deep(value, level) {
            return Err(JsonEmitError::NestingTooDeep);
        }
        match value {
            JsonValue::Null => Ok("null".to_owned()),
            JsonValue::Bool(flag) => Ok(flag.to_string()),
            JsonValue::Integer(number) => self.integer(number),
            JsonValue::Float(number) => self.float(*number),
            JsonValue::String(text) => Ok(json_string(text, self.escaping)),
            JsonValue::Utf16(units) => json_utf16_string(units, self.escaping),
            JsonValue::Array(items) => {
                let members = items
                    .iter()
                    .map(|item| self.value(item, level + 1))
                    .collect::<Result<Vec<_>, _>>()?;
                Ok(self.container(('[', ']'), members, level))
            }
            JsonValue::Object(entries) => self.object(entries, level),
        }
    }

    fn object(
        &self,
        entries: &[(String, JsonValue)],
        level: usize,
    ) -> Result<String, JsonEmitError> {
        let mut ordered: Vec<&(String, JsonValue)> = entries.iter().collect();
        if self.sort_keys {
            ordered.sort_by(|left, right| left.0.cmp(&right.0));
        }
        let members = ordered
            .into_iter()
            .map(|(key, item)| {
                Ok(format!(
                    "{}{}{}",
                    json_string(key, self.escaping),
                    self.key_separator,
                    self.value(item, level + 1)?
                ))
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(self.container(('{', '}'), members, level))
    }

    fn container(&self, brackets: (char, char), members: Vec<String>, level: usize) -> String {
        if members.is_empty() {
            return format!("{}{}", brackets.0, brackets.1);
        }
        let opening = self.newline(level + 1);
        let separator = format!("{}{opening}", self.item_separator);
        let closing = self.newline(level);
        format!(
            "{}{opening}{}{closing}{}",
            brackets.0,
            members.join(&separator),
            brackets.1
        )
    }
}

pub(crate) fn emit(value: &JsonValue, dialect: &JsonDialect) -> Result<String, JsonEmitError> {
    Layout::new(dialect).value(value, 0)
}
