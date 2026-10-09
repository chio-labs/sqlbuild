//! Python's raw and quoted SQL argument patterns and argument value rendering.

use sqlbuild_core::text::main::is_python_space::is_python_space;

use crate::audits::models::ArgumentValue;

/// One `@name` or `@'name'` occurrence, in byte offsets.
pub(crate) struct ParameterMatch<'sql> {
    pub(crate) name: &'sql str,
    pub(crate) start: usize,
    pub(crate) end: usize,
    pub(crate) quoted: bool,
}

/// Every parameter in start order.
pub(crate) fn parameter_matches(sql: &str) -> Vec<ParameterMatch<'_>> {
    let bytes: &[u8] = sql.as_bytes();
    let mut matches: Vec<ParameterMatch<'_>> = Vec::new();
    let mut quoted_end: usize = 0;
    let mut raw_end: usize = 0;
    for (index, byte) in bytes.iter().enumerate() {
        if *byte != b'@'
            || index
                .checked_sub(1)
                .is_some_and(|previous| bytes[previous] == b'@')
        {
            continue;
        }
        if bytes.get(index + 1) == Some(&b'\'') {
            if index < quoted_end {
                continue;
            }
            if let Some(end) = identifier_end(bytes, index + 2)
                && bytes.get(end) == Some(&b'\'')
            {
                matches.push(ParameterMatch {
                    name: &sql[index + 2..end],
                    start: index,
                    end: end + 1,
                    quoted: true,
                });
                quoted_end = end + 1;
            }
            continue;
        }
        if index < raw_end {
            continue;
        }
        let Some(end) = identifier_end(bytes, index + 1) else {
            continue;
        };
        if !opens_call(sql, end) {
            matches.push(ParameterMatch {
                name: &sql[index + 1..end],
                start: index,
                end,
                quoted: false,
            });
            raw_end = end;
        }
    }
    matches
}

/// Python's `render_sql_argument_value` for one value; `None` where it holds an opaque value.
pub(crate) fn render_value(value: &ArgumentValue, quoted: bool) -> Option<String> {
    Some(match value {
        ArgumentValue::List(items) | ArgumentValue::Tuple(items) => items
            .iter()
            .map(|item| render_value(item, quoted))
            .collect::<Option<Vec<String>>>()?
            .join(", "),
        ArgumentValue::Boolean(true) => "TRUE".to_owned(),
        ArgumentValue::Boolean(false) => "FALSE".to_owned(),
        ArgumentValue::Null => "NULL".to_owned(),
        ArgumentValue::Number(text) => text.clone(),
        ArgumentValue::Text(text) if quoted => format!("'{}'", text.replace('\'', "''")),
        ArgumentValue::Text(text) => text.clone(),
        ArgumentValue::Opaque => return None,
    })
}

/// The end of `[A-Za-z_][A-Za-z0-9_]*` at `start`.
fn identifier_end(bytes: &[u8], start: usize) -> Option<usize> {
    let first: u8 = *bytes.get(start)?;
    if !(first.is_ascii_alphabetic() || first == b'_') {
        return None;
    }
    let mut end: usize = start + 1;
    while bytes
        .get(end)
        .is_some_and(|byte| byte.is_ascii_alphanumeric() || *byte == b'_')
    {
        end += 1;
    }
    Some(end)
}

/// Python's `(?=\s*\()` after a name, with `\s` matching what `str.isspace` accepts.
fn opens_call(sql: &str, end: usize) -> bool {
    sql[end..]
        .chars()
        .find(|character| !is_python_space(*character))
        == Some('(')
}

/// Why rendering stops: a missing argument or a value that cannot be rendered.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum RenderStop {
    MissingArgument(String),
    /// The argument whose value cannot be rendered.
    UnsupportedValue(String),
}

/// `render_parameterized_sql` without `reject_unused`.
pub(crate) fn render_parameterized_sql(
    sql: &str,
    arguments: &[(String, ArgumentValue)],
) -> Result<String, RenderStop> {
    let matches = parameter_matches(sql);
    let mut rendered: String = String::with_capacity(sql.len());
    let mut previous_end: usize = 0;
    for item in &matches {
        let Some((_, value)) = arguments
            .iter()
            .find(|(name, _)| name.as_str() == item.name)
        else {
            return Err(RenderStop::MissingArgument(item.name.to_owned()));
        };
        rendered.push_str(&sql[previous_end..item.start]);
        let Some(text) = render_value(value, item.quoted) else {
            return Err(RenderStop::UnsupportedValue(item.name.to_owned()));
        };
        rendered.push_str(&text);
        previous_end = item.end;
    }
    rendered.push_str(&sql[previous_end..]);
    Ok(rendered)
}
