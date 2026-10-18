//! Serialize a [`JsonValue`] in the layout of one Python serializer.

use crate::json::_helpers::floats::{orjson_text, python_repr};
use crate::json::_helpers::strings::{StringEscaping, with_json_string, with_json_utf16_string};
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

    fn with_newline(&self, mut output: String, level: usize) -> String {
        if let Some(indent) = self.indent {
            output.push('\n');
            for _ in 0..level {
                output.push_str(indent);
            }
        }
        output
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

    fn with_value(
        &self,
        mut output: String,
        value: &JsonValue,
        level: usize,
    ) -> Result<String, JsonEmitError> {
        if self.too_deep(value, level) {
            return Err(JsonEmitError::NestingTooDeep);
        }
        match value {
            JsonValue::Null => output.push_str("null"),
            JsonValue::Bool(flag) => output.push_str(if *flag { "true" } else { "false" }),
            JsonValue::Integer(number) => output.push_str(&self.integer(number)?),
            JsonValue::Float(number) => output.push_str(&self.float(*number)?),
            JsonValue::String(text) => return Ok(with_json_string(output, text, self.escaping)),
            JsonValue::Utf16(units) => {
                return with_json_utf16_string(output, units, self.escaping);
            }
            JsonValue::Array(items) => return self.with_array(output, items, level),
            JsonValue::Object(entries) => return self.with_object(output, entries, level),
        }
        Ok(output)
    }

    /// `output` followed by the text before the member at `index` of a container at `level`.
    fn with_separator(&self, mut output: String, index: usize, level: usize) -> String {
        if index > 0 {
            output.push_str(self.item_separator);
        }
        self.with_newline(output, level + 1)
    }

    fn with_array(
        &self,
        mut output: String,
        items: &[JsonValue],
        level: usize,
    ) -> Result<String, JsonEmitError> {
        if items.is_empty() {
            output.push_str("[]");
            return Ok(output);
        }
        output.push('[');
        for (index, item) in items.iter().enumerate() {
            output = self.with_separator(output, index, level);
            output = self.with_value(output, item, level + 1)?;
        }
        output = self.with_newline(output, level);
        output.push(']');
        Ok(output)
    }

    fn with_object(
        &self,
        mut output: String,
        entries: &[(String, JsonValue)],
        level: usize,
    ) -> Result<String, JsonEmitError> {
        if entries.is_empty() {
            output.push_str("{}");
            return Ok(output);
        }
        let mut ordered: Vec<&(String, JsonValue)> = entries.iter().collect();
        if self.sort_keys {
            ordered.sort_by(|left, right| left.0.cmp(&right.0));
        }
        output.push('{');
        for (index, (key, item)) in ordered.into_iter().enumerate() {
            output = self.with_separator(output, index, level);
            output = with_json_string(output, key, self.escaping);
            output.push_str(self.key_separator);
            output = self.with_value(output, item, level + 1)?;
        }
        output = self.with_newline(output, level);
        output.push('}');
        Ok(output)
    }
}

pub(crate) fn emit(value: &JsonValue, dialect: &JsonDialect) -> Result<String, JsonEmitError> {
    Layout::new(dialect).with_value(String::new(), value, 0)
}
