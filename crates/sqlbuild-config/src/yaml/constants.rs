//! YAML 1.2 core schema tags and words, and the limits on one document.

pub(crate) const STANDARD_TAG_PREFIX: &str = "tag:yaml.org,2002:";
pub(crate) const NULL_TAG: &str = "tag:yaml.org,2002:null";
pub(crate) const BOOL_TAG: &str = "tag:yaml.org,2002:bool";
pub(crate) const INT_TAG: &str = "tag:yaml.org,2002:int";
pub(crate) const FLOAT_TAG: &str = "tag:yaml.org,2002:float";
pub(crate) const STR_TAG: &str = "tag:yaml.org,2002:str";
pub(crate) const MERGE_TAG: &str = "tag:yaml.org,2002:merge";
pub(crate) const SEQ_TAG: &str = "tag:yaml.org,2002:seq";
pub(crate) const MAP_TAG: &str = "tag:yaml.org,2002:map";
pub(crate) const NON_SPECIFIC_TAG: &str = "!";
pub(crate) const MAX_NESTING_DEPTH: usize = 256;
pub(crate) const BOOL_WORDS: [(&str, bool); 6] = [
    ("true", true),
    ("True", true),
    ("TRUE", true),
    ("false", false),
    ("False", false),
    ("FALSE", false),
];
pub(crate) const NULL_WORDS: [&str; 5] = ["", "~", "null", "Null", "NULL"];
pub(crate) const INFINITY_WORDS: [&str; 3] = [".inf", ".Inf", ".INF"];
pub(crate) const NAN_WORDS: [&str; 3] = [".nan", ".NaN", ".NAN"];
pub(crate) const MERGE_KEY: &str = "<<";
pub(crate) const MAX_CONSTRUCTION_DEPTH: usize = 256;
pub(crate) const BASE_EXPANSION_BUDGET: usize = 100_000;
pub(crate) const EXPANSION_BUDGET_PER_CHARACTER: usize = 16;
/// Python converts integer text of at most this many digits.
pub(crate) const MAX_INTEGER_DIGITS: usize = 4_300;
