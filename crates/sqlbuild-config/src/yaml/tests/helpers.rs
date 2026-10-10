use crate::errors::ConfigErrorKind;
use crate::models::{ComposedYamlNode, ConfigDate, ConfigDateTime, ConfigTime, ConfigValue};
use crate::yaml::main::compose_marks::compose_marks;

pub(super) fn text(value: &str) -> ConfigValue {
    ConfigValue::String(value.to_owned())
}

/// A one-entry mapping `{"a": value}`.
pub(super) fn under_a(value: ConfigValue) -> ConfigValue {
    ConfigValue::Map(vec![(text("a"), value)])
}

pub(super) fn mapping(entries: Vec<(ConfigValue, ConfigValue)>) -> ConfigValue {
    ConfigValue::Map(entries)
}

pub(super) fn datetime(parts: [u32; 7], utc_offset_seconds: Option<i32>) -> ConfigValue {
    ConfigValue::DateTime(ConfigDateTime {
        date: date_parts(parts[0], parts[1], parts[2]),
        time: ConfigTime {
            hour: u8::try_from(parts[3]).unwrap_or_default(),
            minute: u8::try_from(parts[4]).unwrap_or_default(),
            second: u8::try_from(parts[5]).unwrap_or_default(),
            microsecond: parts[6],
        },
        utc_offset_seconds,
    })
}

pub(super) fn date(year: u32, month: u32, day: u32) -> ConfigValue {
    ConfigValue::Date(date_parts(year, month, day))
}

fn date_parts(year: u32, month: u32, day: u32) -> ConfigDate {
    ConfigDate {
        year: u16::try_from(year).unwrap_or_default(),
        month: u8::try_from(month).unwrap_or_default(),
        day: u8::try_from(day).unwrap_or_default(),
    }
}

/// `a0` holds a list, and every later key nests the previous one through an alias.
pub(super) fn alias_chain(links: usize) -> String {
    (1..links).fold("a0: &a0 [x]\n".to_owned(), |text, link| {
        format!("{text}a{link}: &a{link} [*a{}]\n", link - 1)
    })
}

/// Each level lists the previous level ten times through aliases.
pub(super) fn billion_laughs(levels: usize) -> String {
    (1..levels).fold("a0: &a0 \"lol\"\n".to_owned(), |text, level| {
        let alias = format!("*a{}", level - 1);
        format!(
            "{text}a{level}: &a{level} [{}]\n",
            vec![alias; 10].join(", ")
        )
    })
}

/// Each level merges the previous level twice, doubling the merged entries.
pub(super) fn merge_chain(levels: usize) -> String {
    (1..levels).fold("m0: &m0 {k0: 1}\n".to_owned(), |text, level| {
        let previous = level - 1;
        format!("{text}m{level}: &m{level} {{<<: [*m{previous}, *m{previous}], k{level}: 1}}\n")
    })
}

/// Each anchor wraps the previous one in `depth` flow sequences.
pub(super) fn deep_anchor_chain(links: usize, depth: usize) -> String {
    let (open, close) = ("[".repeat(depth), "]".repeat(depth));
    (1..links).fold(format!("a0: &a0 {open}x{close}\n"), |text, link| {
        format!("{text}a{link}: &a{link} {open}*a{}{close}\n", link - 1)
    })
}

/// `(start, end, value)` of every scalar node, sorted, or the composer's error kind.
pub(super) fn scalar_marks(text: &str) -> Result<Vec<(usize, usize, String)>, ConfigErrorKind> {
    compose_marks(text)
        .map(|document| {
            let mut found: Vec<(usize, usize, String)> =
                document.nodes.iter().filter_map(scalar_mark).collect();
            found.sort();
            found
        })
        .map_err(|error| error.kind)
}

fn scalar_mark(node: &ComposedYamlNode) -> Option<(usize, usize, String)> {
    node.content
        .as_scalar()
        .map(|value| (node.start, node.end, value.to_owned()))
}

pub(super) fn owned_marks(
    marks: Result<&[(usize, usize, &str)], ConfigErrorKind>,
) -> Result<Vec<(usize, usize, String)>, ConfigErrorKind> {
    marks.map(|items| {
        items
            .iter()
            .map(|(start, end, value)| (*start, *end, (*value).to_owned()))
            .collect()
    })
}
