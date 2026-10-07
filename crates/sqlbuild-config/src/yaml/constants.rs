//! YAML tags SafeLoader resolves and constructs.

pub(crate) const NULL_TAG: &str = "tag:yaml.org,2002:null";
pub(crate) const BOOL_TAG: &str = "tag:yaml.org,2002:bool";
pub(crate) const INT_TAG: &str = "tag:yaml.org,2002:int";
pub(crate) const FLOAT_TAG: &str = "tag:yaml.org,2002:float";
pub(crate) const STR_TAG: &str = "tag:yaml.org,2002:str";
pub(crate) const TIMESTAMP_TAG: &str = "tag:yaml.org,2002:timestamp";
pub(crate) const MERGE_TAG: &str = "tag:yaml.org,2002:merge";
pub(crate) const VALUE_TAG: &str = "tag:yaml.org,2002:value";
pub(crate) const SEQ_TAG: &str = "tag:yaml.org,2002:seq";
pub(crate) const MAP_TAG: &str = "tag:yaml.org,2002:map";
pub(crate) const NON_SPECIFIC_TAG: &str = "!";
pub(crate) const PYTHON_ONLY_TAGS: [&str; 4] = [
    "tag:yaml.org,2002:binary",
    "tag:yaml.org,2002:set",
    "tag:yaml.org,2002:omap",
    "tag:yaml.org,2002:pairs",
];
pub(crate) const MAX_NESTING_DEPTH: usize = 256;
pub(crate) const PYTHON_ONLY_LINE_BREAKS: [char; 3] = ['\u{85}', '\u{2028}', '\u{2029}'];
pub(crate) const BOOL_WORDS: [(&str, bool); 18] = [
    ("yes", true),
    ("Yes", true),
    ("YES", true),
    ("no", false),
    ("No", false),
    ("NO", false),
    ("true", true),
    ("True", true),
    ("TRUE", true),
    ("false", false),
    ("False", false),
    ("FALSE", false),
    ("on", true),
    ("On", true),
    ("ON", true),
    ("off", false),
    ("Off", false),
    ("OFF", false),
];
pub(crate) const NULL_WORDS: [&str; 5] = ["", "~", "null", "Null", "NULL"];
pub(crate) const SEXAGESIMAL_BASE: u32 = 60;
pub(crate) const MICROSECOND_DIGITS: usize = 6;
pub(crate) const SECONDS_PER_MINUTE: i32 = 60;
pub(crate) const SECONDS_PER_DAY: i32 = 86_400;
pub(crate) const MERGE_KEY: &str = "<<";
pub(crate) const VALUE_KEY: &str = "=";
pub(crate) const NEGATIVE_SIGN: &str = "-";
pub(crate) const ZERO_TEXT: &str = "0";
pub(crate) const DOCUMENT_END_MARKER: &str = "...";
pub(crate) const LOADER_DEPENDENT_CHARACTERS: [char; 2] = ['\t', crate::constants::BYTE_ORDER_MARK];
pub(crate) const MAX_CONSTRUCTION_DEPTH: usize = 256;
pub(crate) const BASE_EXPANSION_BUDGET: usize = 100_000;
pub(crate) const EXPANSION_BUDGET_PER_CHARACTER: usize = 16;
pub(crate) const PYTHON_INT_MAX_STR_DIGITS: usize = 4_300;
pub(crate) const FLOW_KEY_INDICATOR: char = '?';
pub(crate) const KEEP_INDICATOR: char = '+';
pub(crate) const STRIP_INDICATOR: char = '-';
pub(crate) const SEQUENCE_ENTRY_TOKEN: &str = "-";
pub(crate) const DIRECTIVE_INDICATOR: char = '%';
pub(crate) const PLAIN_FORBIDDEN_FIRST_CHARACTERS: [char; 5] = ['|', '>', '%', '@', '`'];
/// Longer implicit keys are left to Python, which rejects simple keys beyond 1024 characters.
pub(crate) const MAX_NATIVE_IMPLICIT_KEY_CHARACTERS: usize = 1000;
